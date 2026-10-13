"""Scoped UAT recipe governance. Approval and explicit publication are separate."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import select, or_, text, func
from sqlalchemy.orm import selectinload
from app.config import settings
from app.database import AsyncSessionLocal, active_identity_session_factory, active_takeaway_service_session_factory
from app.models.recipe_review import RecipeReview
from app.models.restaurant import Brand, BrandBranch, Recipe
from app.models.product import Product
from app.models.takeaway import TakeawayRecipe, TakeawayRecipeIngredient, TakeawayCatalogItem, TakeawayStockBalance
from app.schemas.recipe_review import RecipeProposal
from app.services.recipe_service import unit_conversion_factor

PERMISSIONS = {"restaurant": "fb.recipe.manage", "takeaway": "takeaway.production.manage"}

def can_manage(current):
    return "*" in current.permissions or ("company" in current.scope_types
        and "company.kitchen.manage" in current.permissions and not current.station_key)

def access(current, system):
    host = urlparse(settings.saas_public_base_url).hostname or ""
    if settings.environment == "production" or not (host.startswith("uat-") or host in {"localhost", "127.0.0.1"}):
        raise HTTPException(403, "ทะเบียนอนุมัติสูตรเปิดเฉพาะ UAT")
    if system not in PERMISSIONS or current.station_key:
        raise HTTPException(403, "เลือกบริบทบริษัทหรือสาขา ไม่ใช่จุดขาย")
    if not can_manage(current) and (PERMISSIONS[system] not in current.permissions or not current.branch_id or not current.brand_id):
        raise HTTPException(403, "ต้องมีสิทธิ์จัดการสูตรและเลือกแบรนด์/สาขาของตน")

async def scope(current, system, brand_id, branch_id=None, *, write=False):
    access(current, system)
    if not can_manage(current):
        if brand_id != current.brand_id or (branch_id != current.branch_id and (write or branch_id is not None)):
            raise HTTPException(403, "จัดการได้เฉพาะสูตรของแบรนด์และสาขาตน")
    async with active_identity_session_factory()() as db:
        brand = await db.scalar(select(Brand).where(Brand.id==brand_id, Brand.company_id==current.company_id,
            Brand.business_type==system, Brand.is_active.is_(True)))
        if not brand:
            raise HTTPException(404, "ไม่พบแบรนด์ในบริษัทและระบบนี้")
        if branch_id and not await db.scalar(select(BrandBranch.id).where(BrandBranch.company_id==current.company_id,
            BrandBranch.brand_id==brand_id, BrandBranch.branch_id==branch_id, BrandBranch.is_active.is_(True))):
            raise HTTPException(404, "สาขาไม่ได้อยู่ในแบรนด์นี้")

def source_factory(system):
    # Restaurant recipe API currently uses get_db (legacy), not the POS service DB.
    if system == "restaurant":
        return AsyncSessionLocal
    try:
        return active_takeaway_service_session_factory()
    except ValueError as exc:
        raise HTTPException(503, "ฐานข้อมูล Takeaway ยังไม่พร้อม") from exc

async def catalog(current, system, brand_id, ids=None, search=""):
    await scope(current, system, brand_id)
    async with source_factory(system)() as db:
        if system=="restaurant":
            q=select(Product).options(selectinload(Product.unit)).where(Product.company_id==current.company_id,
                Product.is_active.is_(True), Product.deleted_at.is_(None), or_(Product.brand_id==brand_id, Product.brand_id.is_(None)))
            model=Product
        else:
            model=TakeawayCatalogItem
            q=select(model).where(model.company_id==current.company_id,model.brand_id==brand_id,model.is_active.is_(True))
        if ids is not None:
            q=q.where(model.id.in_(ids))
        if search:
            q=q.where(or_(model.name.icontains(search,autoescape=True),model.sku.icontains(search,autoescape=True)))
        rows=(await db.scalars(q.order_by(model.name,model.id).limit(250))).all()
        costs = {}
        if system == "takeaway" and rows:
            for item_id, value, quantity in (await db.execute(select(TakeawayStockBalance.item_id,
                func.sum(TakeawayStockBalance.average_cost * TakeawayStockBalance.on_hand_qty),
                func.sum(TakeawayStockBalance.on_hand_qty)).where(TakeawayStockBalance.company_id == current.company_id,
                TakeawayStockBalance.item_id.in_([r.id for r in rows]), TakeawayStockBalance.on_hand_qty > 0)
                .group_by(TakeawayStockBalance.item_id))).all():
                costs[item_id] = str(value / quantity)
        return [{"id":str(r.id), "name":r.name, "sku":r.sku,
            "unit":r.unit.code if system=="restaurant" and r.unit else r.unit if system=="takeaway" else "",
            "reference_cost":str(r.cost_price) if system=="restaurant" else costs.get(r.id)} for r in rows]

async def sources(current, system, brand_id, source_id=None, search=""):
    await scope(current, system, brand_id)
    async with source_factory(system)() as db:
        model=Recipe if system=="restaurant" else TakeawayRecipe
        q=select(model).where(model.company_id==current.company_id,model.brand_id==brand_id)
        if not can_manage(current):
            q=q.where(or_(model.branch_id==current.branch_id,model.branch_id.is_(None)))
        if source_id: q=q.where(model.id==source_id)
        if search: q=q.where(model.name.icontains(search,autoescape=True))
        if system=="restaurant": q=q.options(selectinload(Recipe.ingredients))
        rows=(await db.scalars(q.order_by(model.name,model.version_no.desc(),model.id).limit(200))).all()
        result=[]
        for r in rows:
            lines=r.ingredients if system=="restaurant" else (await db.scalars(select(TakeawayRecipeIngredient)
                .where(TakeawayRecipeIngredient.recipe_id==r.id).order_by(TakeawayRecipeIngredient.sort_order,TakeawayRecipeIngredient.id))).all()
            result.append({"id":str(r.id),"brand_id":str(r.brand_id),"branch_id":str(r.branch_id) if r.branch_id else None,
                "name":r.name,"output_id":str(r.product_id if system=="restaurant" else r.output_item_id),
                "recipe_type":"production" if r.recipe_type in {"production","production_recipe"} else "sale",
                "version_no":r.version_no,"is_active":r.is_active,"yield_qty":str(r.yield_qty),"yield_unit":r.yield_unit,
                "loss_percent":str(r.loss_percent),"effective_from":r.effective_from.isoformat() if r.effective_from else None,
                "effective_to":r.effective_to.isoformat() if r.effective_to else None,
                "ingredients":sorted([{"item_id":str(line.ingredient_id if system=="restaurant" else line.item_id),
                    "quantity":str(line.quantity),"unit":line.unit} for line in lines], key=lambda line:line["item_id"])})
        return result

async def validate_proposal(current, row, *, complete=False):
    payload=RecipeProposal.model_validate(row.proposal)
    ids={payload.output_id,*[i.item_id for i in payload.ingredients if i.item_id]}
    items={r["id"]:r for r in await catalog(current,row.system,row.brand_id,ids)}
    if set(items) != {str(i) for i in ids}:
        raise HTTPException(422,"สินค้าหรือวัตถุดิบไม่ได้อยู่ในแบรนด์/บริษัทนี้ หรือปิดใช้งานแล้ว")
    costs=[]
    try:
        unit_conversion_factor(payload.yield_unit,items[str(payload.output_id)]["unit"])
        for i in payload.ingredients:
            if not i.item_id:
                if complete: raise HTTPException(409,"ยังมีวัตถุดิบขอเพิ่มที่ไม่ได้จับคู่กับรายการอนุมัติ")
                costs.append(None)
                continue
            item=items[str(i.item_id)]
            factor=unit_conversion_factor(i.unit,item["unit"])
            costs.append(str(i.quantity*factor*Decimal(item["reference_cost"])) if item["reference_cost"] is not None else None)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    if complete:
        async with source_factory(row.system)() as db:
            try:
                if row.system=="restaurant":
                    from app.services.recipe_service import RecipeService
                    await RecipeService(db)._validate_no_recipe_cycle(current.company_id,payload.output_id,
                        [i.item_id for i in payload.ingredients],row.branch_id,row.brand_id,row.source_id)
                else:
                    from app.services.takeaway_service import TakeawayService
                    if await TakeawayService(db,current)._recipe_would_cycle(brand_id=row.brand_id,
                        output_item_id=payload.output_id,ingredient_ids={i.item_id for i in payload.ingredients}):
                        raise HTTPException(422,"ส่วนผสมทำให้สูตรวนกลับหาตัวเอง")
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from exc
    return {"items":list(items.values()),"ingredient_reference_costs":costs,
        "batch_reference_cost":str(sum(Decimal(c) for c in costs)) if all(c is not None for c in costs) else None,
        "notice":"Restaurant ใช้ราคาตั้งต้นสินค้า; Takeaway ใช้ต้นทุนเฉลี่ยถ่วงน้ำหนักสต๊อกคงเหลือ หากไม่มีสต๊อกจะแสดงว่าไม่ทราบ ไม่ใช่ต้นทุนผลิตจริง"}

def visible(current):
    q=select(RecipeReview).where(RecipeReview.company_id==current.company_id)
    if not can_manage(current):
        q=q.where(RecipeReview.brand_id==current.brand_id,RecipeReview.branch_id==current.branch_id)
    return q

def serial(row):
    return {k:getattr(row,k) for k in ("id","company_id","brand_id","branch_id","system","source_id","created_by",
        "status","revision","baseline","proposal","history","publication","created_at","updated_at")}

def event(row,current,action,reason,**extra):
    row.history=[*row.history,{"action":action,"reason":reason,"actor_id":str(current.user_id),
        "at":datetime.now().astimezone().isoformat(),"revision":row.revision,"proposal":row.proposal,**extra}]

async def create(db,current,payload):
    await scope(current,payload.system,payload.brand_id,payload.branch_id,write=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key":f"recipe-review:{current.company_id}:{payload.request_key}"})
    old=await db.scalar(select(RecipeReview).where(RecipeReview.company_id==current.company_id,RecipeReview.request_key==payload.request_key))
    if old:
        original=old.history[0].get("request")
        if original != payload.model_dump(mode="json") or old.created_by!=current.user_id:
            raise HTTPException(409,"รหัสคำขอนี้เคยใช้กับข้อมูลอื่นแล้ว")
        return serial(old)
    baseline={}
    if payload.source_id:
        found=await sources(current,payload.system,payload.brand_id,payload.source_id)
        if not found: raise HTTPException(404,"ไม่พบสูตรต้นฉบับ")
        baseline=found[0]
        if baseline["output_id"]!=str(payload.proposal.output_id):
            raise HTTPException(422,"ห้ามเปลี่ยนสินค้าผลลัพธ์ของสูตรเดิม")
    row=RecipeReview(company_id=current.company_id,brand_id=payload.brand_id,branch_id=payload.branch_id,
        system=payload.system,source_id=payload.source_id,request_key=payload.request_key,created_by=current.user_id,
        baseline=baseline,proposal=payload.proposal.model_dump(mode="json"),history=[],status="draft",revision=1)
    evidence=await validate_proposal(current,row)
    event(row,current,"create",payload.proposal.reason,request=payload.model_dump(mode="json"),reference=evidence)
    db.add(row); await db.commit(); await db.refresh(row)
    return serial(row)

def transition_allowed(row,current,action):
    owner=row.created_by==current.user_id
    if action in {"save","submit"}:
        if not owner or row.status not in {"draft","returned"}:
            raise HTTPException(409,"เฉพาะผู้เสนอแก้ไขหรือส่งร่างของตนได้")
    elif action in {"approve","reject","return","resolve","material","publish"}:
        if not can_manage(current) or owner:
            raise HTTPException(403,"ต้องเป็นแอดมินครัวกลางระดับบริษัทคนละคนกับผู้เสนอ")
        allowed = {"approved_hold", "published"} if action == "publish" else {"submitted"}
        if row.status not in allowed: raise HTTPException(409,"สถานะคำขอไม่รองรับการดำเนินการนี้")

async def act(db,current,id,payload):
    row=await db.scalar(visible(current).where(RecipeReview.id==id).with_for_update())
    if not row: raise HTTPException(404,"ไม่พบคำขอ")
    await scope(current,row.system,row.brand_id,row.branch_id,write=True)
    if row.revision!=payload.revision: raise HTTPException(409,"มีผู้แก้ไขคำขอนี้แล้ว กรุณาโหลดใหม่")
    transition_allowed(row,current,payload.action)
    if payload.action == "publish" and row.status == "published":
        return serial(row)
    if payload.action=="save":
        if not payload.proposal: raise HTTPException(422,"กรุณาระบุสูตร")
        if payload.proposal.output_id != UUID(row.proposal["output_id"]): raise HTTPException(422,"ห้ามเปลี่ยนสินค้าผลลัพธ์")
        row.proposal=payload.proposal.model_dump(mode="json")
    elif payload.action=="resolve":
        lines=[dict(i) for i in row.proposal["ingredients"]]
        if payload.line_index is None or payload.line_index>=len(lines) or not payload.item_id:
            raise HTTPException(422,"เลือกวัตถุดิบขอเพิ่มและรายการที่อนุมัติแล้ว")
        line=lines[payload.line_index]
        if line["item_id"]: raise HTTPException(409,"รายการนี้จับคู่แล้ว")
        line["item_id"]=str(payload.item_id)
        row.proposal={**row.proposal,"ingredients":lines}
        from pydantic import ValidationError
        try:
            RecipeProposal.model_validate(row.proposal)
        except ValidationError as exc:
            raise HTTPException(422,"จับคู่แล้ววัตถุดิบซ้ำหรือไม่ถูกต้อง กรุณาตรวจร่าง") from exc
    if payload.action == "material":
        from app.services.recipe_publication_service import material
        await material(db,current,row,payload)
        RecipeProposal.model_validate(row.proposal)
        evidence = {"notice": "ตรวจวัตถุดิบกลางแล้ว ไม่สร้างยอดสต๊อก"}
    else:
        evidence=await validate_proposal(current,row,complete=payload.action=="approve")
    if payload.action in {"submit","approve"} and row.source_id:
        now=await sources(current,row.system,row.brand_id,row.source_id)
        if not now or now[0]!=row.baseline:
            raise HTTPException(409,"สูตรต้นฉบับเปลี่ยนแล้ว ให้สร้างคำขอใหม่จากสูตรล่าสุด")
    row.status={"save":"draft","submit":"submitted","approve":"approved_hold","return":"returned","reject":"rejected"}.get(payload.action,row.status)
    if payload.action == "approve" and row.proposal["recipe_type"] == "production":
        from app.services.recipe_publication_service import canonical_snapshot
        # Existing pilot approvals remain held until their mapping is reviewed.
        await canonical_snapshot(db,row)
    if payload.action == "publish":
        from app.services.recipe_publication_service import publish
        await publish(db,current,row)
    row.revision+=1
    event(row,current,payload.action,payload.reason,reference=evidence)
    await db.commit(); await db.refresh(row)
    return serial(row)
