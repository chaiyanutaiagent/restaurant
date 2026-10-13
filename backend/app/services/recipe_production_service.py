"""Single raw-material ledger for both systems; durable, idempotent output delivery.

No call to a Takeaway raw stock decrement is made here. A committed raw issue is
never repeated on retry, even when the destination database is unavailable.
"""
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, or_
from app.config import settings
from app.database import active_identity_session_factory
from app.models.restaurant import Brand, Recipe
from app.models.recipe_review import RecipeReview, RecipeProductionRun
from app.models.shared_kitchen import CompanyKitchen, CompanyIngredientLot, CompanyKitchenMovement
from app.models.stock import StockLocation, StockBalance, StockMovement
from app.models.product import Product
from app.models.takeaway import TakeawayStockLocation, TakeawayRecipe, TakeawayCatalogItem
from app.services import recipe_review_service as review
from app.services.recipe_publication_service import lock, today
from app.services.recipe_service import unit_conversion_factor

Q = Decimal("0.0001")


def authorize(current):
    review.access(current, "restaurant")
    if not review.can_manage(current) or not settings.company_kitchen_writes_enabled:
        raise HTTPException(403, "ต้องมีสิทธิ์แอดมินครัวกลางและเปิดธุรกรรมครัวกลาง UAT")


async def locations(current, system, brand_id):
    await review.scope(current, system, brand_id)
    async with active_identity_session_factory()() as identity:
        brand = await identity.get(Brand, brand_id)
        central_branch = brand.central_branch_id
        ready = brand.central_ready_location_id
    async with review.source_factory(system)() as source:
        model = StockLocation if system == "restaurant" else TakeawayStockLocation
        q = select(model).where(model.company_id == current.company_id, model.is_active.is_(True))
        if system == "restaurant":
            q = q.where(model.id == ready, model.deleted_at.is_(None))
        else:
            if central_branch is None:
                return []
            q = q.where(model.branch_id == central_branch, model.location_type == "central_ready")
        rows = (await source.scalars(q)).all()
        return [{"id": str(r.id), "name": r.name, "branch_id": str(r.branch_id)} for r in rows]


def serial(row):
    return {"id": row.id, "review_id": row.review_id, "brand_id": row.brand_id, "status": row.status,
        "snapshot": row.snapshot, "created_at": row.created_at}


async def produce(db, current, payload):
    authorize(current)
    await lock(db, f"recipe-run:{current.company_id}:{payload.request_key}")
    existing = await db.scalar(select(RecipeProductionRun).where(RecipeProductionRun.company_id == current.company_id,
        RecipeProductionRun.request_key == payload.request_key))
    fingerprint = payload.model_dump(mode="json")
    if existing:
        if existing.snapshot["request"] != fingerprint:
            raise HTTPException(409, "รหัสรายการผลิตนี้ใช้กับข้อมูลอื่นแล้ว")
        await db.commit()
        return await deliver(db, current, existing.id)
    row = await db.scalar(select(RecipeReview).where(RecipeReview.id == payload.review_id,
        RecipeReview.company_id == current.company_id).with_for_update())
    if not row or row.status != "published" or row.proposal["recipe_type"] != "production":
        raise HTTPException(409, "ต้องใช้สูตรผลิตที่อนุมัติและเปิดใช้แล้ว")
    await review.scope(current, row.system, row.brand_id, row.branch_id, write=True)
    allowed = await locations(current, row.system, row.brand_id)
    location = next((l for l in allowed if l["id"] == str(payload.output_location_id)), None)
    if not location:
        raise HTTPException(409, "เลือกคลังสินค้าสำเร็จรูปครัวกลางของแบรนด์นี้")
    async with review.source_factory(row.system)() as source:
        cls = Recipe if row.system == "restaurant" else TakeawayRecipe
        recipe = await source.get(cls, UUID(row.publication["source_id"]))
        if not recipe or not recipe.is_active or recipe.effective_from > today() or (recipe.effective_to and recipe.effective_to <= today()):
            raise HTTPException(409, "สูตรนี้หมดอายุหรือมีเวอร์ชันใหม่แล้ว")
        product = await source.get(Product if row.system == "restaurant" else TakeawayCatalogItem, UUID(row.proposal["output_id"]))
        if not product or not product.is_active:
            raise HTTPException(409, "สินค้าผลผลิตปิดใช้งาน")
    kitchen = await db.scalar(select(CompanyKitchen).where(CompanyKitchen.company_id == current.company_id,
        CompanyKitchen.is_active.is_(True)).with_for_update())
    if not kitchen:
        raise HTTPException(409, "ยังไม่ได้ตั้งครัวกลางบริษัท")
    # Recipe yield denotes actual good output; loss applies exactly once to inputs.
    scale = payload.quantity / Decimal(row.proposal["yield_qty"]) / (1 - Decimal(row.proposal["loss_percent"]) / 100)
    required = {}
    for line in row.publication["canonical_ingredients"]:
        key = UUID(line["canonical_id"])
        required[key] = required.get(key, Decimal(0)) + Decimal(line["quantity"]) * scale
    if not required:
        raise HTTPException(409, "ไม่มีวัตถุดิบกลางในหลักฐานอนุมัติ")
    run = RecipeProductionRun(company_id=current.company_id, brand_id=row.brand_id, review_id=row.id,
        request_key=payload.request_key, created_by=current.user_id, status="output_pending", snapshot={})
    db.add(run); await db.flush()
    allocations, total = [], Decimal(0)
    for ingredient_id in sorted(required, key=str):
        qty = required[ingredient_id].quantize(Q, rounding=ROUND_HALF_UP)
        if qty <= 0:
            raise HTTPException(422, "ปริมาณผลิตน้อยเกินความละเอียดสต๊อก")
        lots = (await db.scalars(select(CompanyIngredientLot).where(CompanyIngredientLot.company_id == current.company_id,
            CompanyIngredientLot.kitchen_id == kitchen.id, CompanyIngredientLot.ingredient_id == ingredient_id,
            CompanyIngredientLot.qty_on_hand > 0,
            or_(CompanyIngredientLot.expires_on.is_(None), CompanyIngredientLot.expires_on >= today()))
            .order_by(CompanyIngredientLot.received_at, CompanyIngredientLot.id).with_for_update())).all()
        if sum((r.qty_on_hand for r in lots), Decimal(0)) < qty:
            raise HTTPException(409, "วัตถุดิบกลางไม่พอ (ไม่นับล็อตหมดอายุ) ต้องรับสินค้าเข้าคลังจริงก่อน")
        for lot in lots:
            if qty <= 0: break
            used = min(qty, lot.qty_on_hand)
            before = lot.qty_on_hand
            lot.qty_on_hand -= used
            qty -= used
            cost = used * lot.unit_cost
            total += cost
            allocations.append({"ingredient_id": str(ingredient_id), "lot_id": str(lot.id), "quantity": str(used), "cost": str(cost)})
            db.add(CompanyKitchenMovement(company_id=current.company_id, kitchen_id=kitchen.id, ingredient_id=ingredient_id,
                lot_id=lot.id, location_id=kitchen.raw_location_id, brand_id=row.brand_id,
                movement_type="production_issue", qty=-used, qty_before=before, qty_after=lot.qty_on_hand, unit_cost=lot.unit_cost,
                idempotency_key=f"recipe-run:{run.id}:{lot.id}", reference_type="recipe_production_run", reference_id=str(run.id),
                note=payload.reason, actor_id=current.user_id))
    output_items = await review.catalog(current, row.system, row.brand_id, [UUID(row.proposal["output_id"])])
    if len(output_items) != 1:
        raise HTTPException(409, "ไม่พบสินค้าผลผลิต")
    stock_qty = (payload.quantity * unit_conversion_factor(row.proposal["yield_unit"], output_items[0]["unit"])).quantize(Q)
    if stock_qty <= 0:
        raise HTTPException(422, "ผลผลิตน้อยกว่าความละเอียดสต๊อก")
    run.snapshot = {"request": fingerprint, "system": row.system, "publication": row.publication,
        "output_item_id": row.proposal["output_id"], "output_location_id": str(payload.output_location_id),
        "output_branch_id": location["branch_id"], "stock_quantity": str(stock_qty), "allocations": allocations,
        "total_cost": str(total), "unit_cost": str((total / stock_qty).quantize(Q))}
    await db.commit()
    # If this fails, raw evidence remains output_pending, explicitly shown in UI.
    return await deliver(db, current, run.id)


async def deliver(db, current, run_id):
    authorize(current)
    run = await db.scalar(select(RecipeProductionRun).where(RecipeProductionRun.id == run_id,
        RecipeProductionRun.company_id == current.company_id).with_for_update())
    if not run:
        raise HTTPException(404, "ไม่พบรายการผลิต")
    if run.status == "completed":
        return serial(run)
    s = run.snapshot
    async with review.source_factory(s["system"])() as source:
        await lock(source, f"recipe-output:{run.id}")
        # Serialise output balance creation as nullable-variant unique constraints
        # alone do not protect concurrent first receipts on PostgreSQL 14.
        await lock(source, f"recipe-balance:{s['output_location_id']}:{s['output_item_id']}")
        if s["system"] == "takeaway":
            from app.services.takeaway_service import TakeawayService
            await TakeawayService(source, current)._apply_stock(location_id=UUID(s["output_location_id"]),
                item_id=UUID(s["output_item_id"]), lot_code=f"RV-{run.id}", quantity_delta=Decimal(s["stock_quantity"]),
                unit_cost=Decimal(s["unit_cost"]), movement_type="production_output", idempotency_key=f"recipe-output:{run.id}",
                brand_id=run.brand_id, branch_id=UUID(s["output_branch_id"]), note="Approved shared-kitchen recipe")
        else:
            prior = await source.scalar(select(StockMovement.id).where(StockMovement.company_id == current.company_id,
                StockMovement.reference_type == "recipe_production_run", StockMovement.reference_id == str(run.id)))
            if not prior:
                from app.services.stock_service import StockService
                balance = await source.scalar(select(StockBalance).where(StockBalance.company_id == current.company_id,
                    StockBalance.location_id == UUID(s["output_location_id"]), StockBalance.product_id == UUID(s["output_item_id"]),
                    StockBalance.variant_id.is_(None)).with_for_update())
                if not balance:
                    balance = StockBalance(company_id=current.company_id, branch_id=UUID(s["output_branch_id"]),
                        location_id=UUID(s["output_location_id"]), product_id=UUID(s["output_item_id"]),
                        qty_on_hand=0, qty_reserved=0, cost_per_unit=0)
                    source.add(balance); await source.flush()
                await StockService(source)._record_movement(balance, "receive", Decimal(s["stock_quantity"]), run.created_by,
                    cost_per_unit=Decimal(s["unit_cost"]), reference_type="recipe_production_run", reference_id=str(run.id))
        await source.commit()
    run.status = "completed"
    await db.commit()
    return serial(run)
