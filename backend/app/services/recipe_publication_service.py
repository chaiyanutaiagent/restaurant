"""UAT recipe publication. Never mutate a BOM already referenced by a transaction.

The source DB and review DB need not be the same. Source IDs are deterministic,
and their content is checked on retry after an uncertain cross-DB commit.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, func, text

from app.models.product import Product, Unit
from app.models.restaurant import Recipe, RecipeIngredient
from app.models.shared_kitchen import CompanyIngredient
from app.models.takeaway import TakeawayCatalogItem, TakeawayRecipe, TakeawayRecipeIngredient
from app.models.recipe_review import RecipeReview, RecipeLegacyRegistration
from app.services import recipe_review_service as review
from app.services.recipe_service import unit_conversion_factor


def today():
    return datetime.now(ZoneInfo("Asia/Bangkok")).date()


async def lock(db, key):
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": key})


async def canonical_options(db, current):
    review.access(current, "restaurant" if review.can_manage(current) else ("takeaway" if "takeaway.production.manage" in current.permissions else "restaurant"))
    rows = (await db.scalars(select(CompanyIngredient).where(
        CompanyIngredient.company_id == current.company_id, CompanyIngredient.is_active.is_(True))
        .order_by(CompanyIngredient.name))).all()
    return [{"id": r.id, "name": r.name, "unit": r.base_unit_code, "code": r.code} for r in rows]


async def material(db, current, row, payload):
    """Manager resolves a line to a Company identity; creates no stock balances."""
    lines = [dict(i) for i in row.proposal["ingredients"]]
    if payload.line_index is None or payload.line_index >= len(lines):
        raise HTTPException(422, "เลือกส่วนผสมที่ต้องการตรวจ")
    line = lines[payload.line_index]
    await lock(db, f"recipe-material:{current.company_id}")
    canonical = None
    if payload.canonical_id:
        canonical = await db.scalar(select(CompanyIngredient).where(
            CompanyIngredient.id == payload.canonical_id, CompanyIngredient.company_id == current.company_id,
            CompanyIngredient.is_active.is_(True)))
        if not canonical:
            raise HTTPException(404, "ไม่พบวัตถุดิบกลางในบริษัท")
    else:
        name = " ".join(line.get("requested_name", "").split())
        if not name or line.get("item_id"):
            raise HTTPException(422, "รายการเดิมให้เลือกวัตถุดิบกลางที่ตรงกัน")
        # Deduplicate names against canonical and unregistered products. Never guess
        # that differently named raw materials are the same physical ingredient.
        canonical = await db.scalar(select(CompanyIngredient).where(
            CompanyIngredient.company_id == current.company_id,
            func.lower(func.regexp_replace(func.trim(CompanyIngredient.name), r"\s+", " ", "g")) == name.lower()))
        if canonical and not canonical.is_active:
            raise HTTPException(409, "วัตถุดิบกลางนี้ปิดใช้งานอยู่")
        if not canonical:
            unit_code = line["unit"].lower()
            if unit_code not in {"kg", "g", "l", "ml", "pcs"}:
                raise HTTPException(422, "วัตถุดิบใหม่ใช้หน่วย kg, g, l, ml หรือ pcs")
            existing = await db.scalar(select(Product).where(Product.company_id == current.company_id,
                Product.deleted_at.is_(None), func.lower(func.regexp_replace(func.trim(Product.name), r"\s+", " ", "g")) == name.lower()))
            if existing:
                raise HTTPException(409, "มีสินค้าชื่อนี้แล้ว ให้ลงทะเบียนเป็นวัตถุดิบกลางก่อน ไม่สร้างรายการซ้ำ")
            identity = uuid5(NAMESPACE_URL, f"review-material:{row.id}:{payload.line_index}")
            unit = await db.scalar(select(Unit).where(Unit.company_id == current.company_id, func.lower(Unit.code) == unit_code))
            if unit and (unit.deleted_at or not unit.is_active):
                raise HTTPException(409, "หน่วยนี้ปิดใช้งาน")
            if not unit:
                unit = Unit(company_id=current.company_id, code=unit_code, name=unit_code, decimal_places=4)
                db.add(unit); await db.flush()
            db.add(Product(id=identity, company_id=current.company_id, brand_id=None, sku=f"RM-{identity.hex}",
                name=name, unit_id=unit.id, product_type="raw_material", inventory_role="central_raw",
                cost_price=0, selling_price=0, vat_type="included", vat_rate=7, is_active=True,
                is_for_sale=False, is_for_purchase=True))
            await db.flush()
            canonical = CompanyIngredient(id=identity, company_id=current.company_id, canonical_product_id=identity,
                code=f"RM-{identity.hex}", name=name, base_unit_code=unit_code,
                unit_dimension="mass" if unit_code in {"kg", "g"} else "volume" if unit_code in {"l", "ml"} else "count", is_active=True)
            db.add(canonical); await db.flush()
    try:
        unit_conversion_factor(line["unit"], canonical.base_unit_code)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not line.get("item_id"):
        if row.system == "restaurant":
            line["item_id"] = str(canonical.canonical_product_id)
        else:
            # Metadata projection only, zero stock. Stable ID permits safe recovery.
            identity = uuid5(NAMESPACE_URL, f"canonical-takeaway:{row.brand_id}:{canonical.id}")
            async with review.source_factory("takeaway")() as source:
                await lock(source, f"review-projection:{row.brand_id}:{canonical.id}")
                item = await source.get(TakeawayCatalogItem, identity)
                if not item:
                    duplicate = await source.scalar(select(TakeawayCatalogItem.id).where(
                        TakeawayCatalogItem.company_id == current.company_id, TakeawayCatalogItem.brand_id == row.brand_id,
                        func.lower(func.trim(TakeawayCatalogItem.name)) == canonical.name.lower()))
                    if duplicate:
                        raise HTTPException(409, "มีรายการ Takeaway ชื่อนี้แล้ว ให้จับคู่รายการเดิมก่อน")
                    source.add(TakeawayCatalogItem(id=identity, company_id=current.company_id, brand_id=row.brand_id,
                        sku=f"RM-{canonical.id.hex}", name=canonical.name, unit=canonical.base_unit_code, price=0,
                        is_active=True, source_metadata={"canonical_ingredient_id": str(canonical.id), "product_type": "raw_material", "is_for_sale": False}))
                    await source.commit()
                elif item.company_id != current.company_id or item.brand_id != row.brand_id or not item.is_active:
                    raise HTTPException(409, "รายการวัตถุดิบที่เคยสร้างไม่ตรงกัน")
            line["item_id"] = str(identity)
    line["canonical_id"] = str(canonical.id)
    row.proposal = {**row.proposal, "ingredients": lines}


async def canonical_snapshot(db, row):
    result = []
    for line in row.proposal["ingredients"]:
        if not line.get("canonical_id"):
            raise HTTPException(409, "สูตรผลิตต้องจับคู่วัตถุดิบกลางทุกส่วนผสมก่อนเปิดใช้")
        item = await db.scalar(select(CompanyIngredient).where(CompanyIngredient.id == UUID(line["canonical_id"]),
            CompanyIngredient.company_id == row.company_id, CompanyIngredient.is_active.is_(True)))
        if not item:
            raise HTTPException(409, "วัตถุดิบกลางปิดใช้หรือไม่อยู่ในบริษัท")
        try:
            factor = unit_conversion_factor(line["unit"], item.base_unit_code)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        result.append({"canonical_id": str(item.id), "item_id": line["item_id"], "name": item.name,
            "quantity": str(Decimal(line["quantity"]) * factor), "unit": item.base_unit_code})
    return result


async def publish(db, current, row):
    if row.status == "published":
        return
    p = row.proposal
    from datetime import date
    if date.fromisoformat(p["effective_from"]) > today():
        raise HTTPException(409, "ยังไม่ถึงวันเริ่มใช้ อนุมัติไว้ก่อนได้แล้วกดเปิดใช้เมื่อถึงกำหนด")
    await review.validate_proposal(current, row, complete=True)
    if row.system == "restaurant":
        async with review.source_factory("restaurant")() as inventory:
            product = await inventory.get(Product, UUID(p["output_id"]))
            if p["recipe_type"] == "sale":
                if product.product_type != "menu_item":
                    raise HTTPException(409, "สูตรประกอบขาย Restaurant ต้องใช้สินค้าประเภทเมนู")
                ingredients = (await inventory.scalars(select(Product).where(Product.id.in_([UUID(l["item_id"]) for l in p["ingredients"]])))).all()
                if any(i.inventory_role not in {"central_ready", "store_local"} for i in ingredients):
                    raise HTTPException(409, "สูตรประกอบขายใช้สินค้าพร้อมขายหรือวัตถุดิบคลังร้านเท่านั้น ไม่ตัดวัตถุดิบครัวกลางซ้ำ")
            elif product.inventory_role != "central_ready":
                raise HTTPException(409, "สินค้าผลผลิตต้องกำหนดเป็นสินค้าสำเร็จรูปครัวกลาง (READY)")
    canonical = await canonical_snapshot(db, row) if p["recipe_type"] == "production" else []
    target_id = uuid5(NAMESPACE_URL, f"approved-recipe:{row.id}")
    model = Recipe if row.system == "restaurant" else TakeawayRecipe
    output = model.product_id if row.system == "restaurant" else model.output_item_id
    recipe_type = ("production_recipe" if p["recipe_type"] == "production" else "menu_recipe") if row.system == "restaurant" else p["recipe_type"]
    async with review.source_factory(row.system)() as source:
        await lock(source, f"recipe-publish:{row.company_id}:{row.brand_id}:{p['output_id']}")
        existing = await source.get(model, target_id)
        if not existing:
            # Optimistic baseline is checked under the same lock as other publications.
            if row.source_id:
                found = await review.sources(current, row.system, row.brand_id, row.source_id)
                if not found or found[0] != row.baseline:
                    raise HTTPException(409, "สูตรต้นฉบับเปลี่ยนหลังอนุมัติ ให้เสนอจากสูตรล่าสุด")
            q = select(model).where(model.company_id == row.company_id, model.brand_id == row.brand_id,
                output == UUID(p["output_id"]), model.branch_id == row.branch_id)
            old = (await source.scalars(q.with_for_update())).all()
            if not row.source_id and any(r.is_active and r.recipe_type == recipe_type for r in old):
                raise HTTPException(409, "มีสูตรใช้งานสำหรับสินค้านี้แล้ว ให้เสนอแก้จากสูตรเดิม")
            version = max((r.version_no for r in old), default=0) + 1
            for r in old:
                if r.recipe_type == recipe_type and r.is_active:
                    r.is_active = False
                    r.effective_to = today()
            kwargs = {"id": target_id, "company_id": row.company_id, "brand_id": row.brand_id, "branch_id": row.branch_id,
                "name": p["name"], "recipe_type": recipe_type, "version_no": version, "yield_qty": Decimal(p["yield_qty"]),
                "yield_unit": p["yield_unit"], "loss_percent": Decimal(p["loss_percent"]), "effective_from": today(), "is_active": True}
            kwargs["product_id" if row.system == "restaurant" else "output_item_id"] = UUID(p["output_id"])
            source.add(model(**kwargs)); await source.flush()
            for n, line in enumerate(p["ingredients"]):
                cls = RecipeIngredient if row.system == "restaurant" else TakeawayRecipeIngredient
                args = {"recipe_id": target_id, "quantity": Decimal(line["quantity"]), "unit": line["unit"], "sort_order": n}
                args["ingredient_id" if row.system == "restaurant" else "item_id"] = UUID(line["item_id"])
                if row.system == "takeaway":
                    item = await source.get(TakeawayCatalogItem, UUID(line["item_id"]))
                    args["sku"] = item.sku
                source.add(cls(**args))
            await source.commit()
        else:
            if existing.company_id != row.company_id or existing.brand_id != row.brand_id:
                raise HTTPException(409, "Publication identity conflict")
            version = existing.version_no
            cls = RecipeIngredient if row.system == "restaurant" else TakeawayRecipeIngredient
            saved_lines = (await source.scalars(select(cls).where(cls.recipe_id == target_id))).all()
            saved = sorted((str(x.ingredient_id if row.system == "restaurant" else x.item_id), Decimal(x.quantity), x.unit) for x in saved_lines)
            expected = sorted((x["item_id"], Decimal(x["quantity"]), x["unit"]) for x in p["ingredients"])
            if saved != expected or existing.name != p["name"] or existing.yield_qty != Decimal(p["yield_qty"]) or existing.loss_percent != Decimal(p["loss_percent"]):
                raise HTTPException(409, "สูตรที่เผยแพร่ไม่ตรงกับหลักฐานอนุมัติ ห้ามเผยแพร่ซ้ำ")
    # A source commit can succeed even if the reply is lost. Deterministic target
    # identity makes this second commit safely retryable, without another version.
    row.publication = {"source_id": str(target_id), "version": version, "effective_from": today().isoformat(),
        "canonical_ingredients": canonical, "stock_owner": "company_kitchen" if canonical else "store",
        "proposal": p, "published_by": str(current.user_id)}
    row.status = "published"


async def register_legacy(db, current, system, brand_id):
    await review.scope(current, system, brand_id)
    if not review.can_manage(current):
        raise HTTPException(403, "เฉพาะแอดมินครัวกลาง")
    await lock(db, f"recipe-register:{current.company_id}:{brand_id}")
    count = 0
    rows = await review.sources(current, system, brand_id)
    if len(rows) == 200:
        raise HTTPException(409, "แบรนด์มีสูตรถึงขีดจำกัด ต้องลงทะเบียนแบบแบ่งหน้าก่อน")
    for row in rows:
        old = await db.scalar(select(RecipeLegacyRegistration).where(RecipeLegacyRegistration.company_id == current.company_id,
            RecipeLegacyRegistration.system == system, RecipeLegacyRegistration.source_id == UUID(row["id"])))
        if not old:
            db.add(RecipeLegacyRegistration(company_id=current.company_id, brand_id=brand_id, system=system,
                source_id=UUID(row["id"]), snapshot=row, registered_by=current.user_id)); count += 1
    await db.commit()
    return {"registered": count, "read": len(rows), "stock_changed": False}
