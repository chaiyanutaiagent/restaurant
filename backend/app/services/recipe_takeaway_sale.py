"""Approved assembly recipes consume STORE stock, never central raw stock.

Refunds already reverse recorded sale movements, so later recipe edits cannot
change what a historical refund restores.
"""
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select, or_
from fastapi import HTTPException
from app.database import AsyncSessionLocal
from app.models.recipe_review import RecipeReview
from app.models.takeaway import TakeawayRecipe, TakeawayRecipeIngredient, TakeawayCatalogItem, TakeawayStockBalance
from app.services.recipe_governance_guard import enabled
from app.services.recipe_publication_service import today, lock
from app.services.recipe_service import unit_conversion_factor


async def consume(service, order, order_item, location_id):
    if not enabled():
        return False
    db = service.db
    recipe = await db.scalar(select(TakeawayRecipe).where(TakeawayRecipe.company_id == order.company_id,
        TakeawayRecipe.brand_id == order.brand_id, TakeawayRecipe.output_item_id == order_item.catalog_item_id,
        TakeawayRecipe.recipe_type == "sale", TakeawayRecipe.is_active.is_(True),
        or_(TakeawayRecipe.branch_id == order.branch_id, TakeawayRecipe.branch_id.is_(None)),
        or_(TakeawayRecipe.effective_from.is_(None), TakeawayRecipe.effective_from <= today()),
        or_(TakeawayRecipe.effective_to.is_(None), TakeawayRecipe.effective_to > today()))
        .order_by(TakeawayRecipe.branch_id.is_not(None).desc(), TakeawayRecipe.version_no.desc()).limit(1))
    if not recipe:
        return False
    async with AsyncSessionLocal() as governance:
        approved = await governance.scalar(select(RecipeReview).where(RecipeReview.company_id == order.company_id,
            RecipeReview.system == "takeaway", RecipeReview.status == "published",
            RecipeReview.publication["source_id"].astext == str(recipe.id)))
    if not approved:
        # Grandfathered legacy recipes are not silently activated as a new sale BOM.
        return False
    output = await db.get(TakeawayCatalogItem, order_item.catalog_item_id)
    scale = (Decimal(order_item.quantity) * unit_conversion_factor(output.unit, recipe.yield_unit)
        / recipe.yield_qty / (1 - recipe.loss_percent / 100))
    lines = (await db.scalars(select(TakeawayRecipeIngredient).where(TakeawayRecipeIngredient.recipe_id == recipe.id)
        .order_by(TakeawayRecipeIngredient.item_id))).all()
    evidence = []
    for line in lines:
        item = await db.get(TakeawayCatalogItem, line.item_id)
        if not item or item.company_id != order.company_id or item.brand_id != order.brand_id or not item.is_active:
            raise HTTPException(409, "วัตถุดิบสูตรประกอบขายปิดใช้หรือไม่ตรงแบรนด์")
        qty = (line.quantity * scale * unit_conversion_factor(line.unit, item.unit)).quantize(Decimal("0.0001"))
        if qty <= 0:
            raise HTTPException(409, "ปริมาณส่วนผสมต่ำกว่าความละเอียดสต๊อก")
        await lock(db, f"recipe-store:{location_id}:{item.id}")
        lots = (await db.scalars(select(TakeawayStockBalance).where(TakeawayStockBalance.company_id == order.company_id,
            TakeawayStockBalance.location_id == location_id, TakeawayStockBalance.item_id == item.id,
            TakeawayStockBalance.on_hand_qty > TakeawayStockBalance.reserved_qty)
            .order_by(TakeawayStockBalance.created_at, TakeawayStockBalance.id).with_for_update())).all()
        if sum((l.on_hand_qty - l.reserved_qty for l in lots), Decimal(0)) < qty:
            raise HTTPException(409, "วัตถุดิบประกอบขายในคลังร้านไม่พอ")
        evidence.append({"item_id": str(item.id), "quantity": str(qty), "unit": item.unit})
        for lot in lots:
            if qty <= 0: break
            use = min(qty, lot.on_hand_qty - lot.reserved_qty)
            qty -= use
            await service._apply_stock(location_id=location_id, item_id=item.id, lot_code=lot.lot_code,
                quantity_delta=-use, unit_cost=lot.average_cost, movement_type="sale",
                idempotency_key=f"recipe-sale:{order.id}:{order_item.id}:{lot.id}",
                brand_id=order.brand_id, branch_id=order.branch_id, order_id=order.id)
    metadata = dict(order.source_metadata or {})
    metadata["recipe_snapshots"] = [*metadata.get("recipe_snapshots", []),
        {"order_item_id": str(order_item.id), "recipe_id": str(recipe.id), "version": recipe.version_no, "ingredients": evidence}]
    order.source_metadata = metadata
    return True
