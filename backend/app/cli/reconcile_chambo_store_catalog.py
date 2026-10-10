"""Idempotent, UAT-only repair of the approved BKK-01 sales assortment.

No ingredients, recipes, costs, stock or historic transactions are removed.
The six imported menus retain their IDs; two explicitly approved menus are added.
"""
import asyncio
import json
import os
import uuid
from decimal import Decimal

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from app.database import TakeawaySessionLocal
from app.models.takeaway import TakeawayCatalogItem, TakeawayCategory, TakeawayBranchCatalogItem, TakeawayReferenceProjection

COMPANY = uuid.UUID("1b8a1818-44d6-4d5f-9d22-e5e17b23c081")
BRAND = uuid.UUID("d6391cbe-ee53-4873-b95b-219c9bc23e7c")
BRANCH = uuid.UUID("1f397253-0479-4970-8288-f72d6cde6d7e")
MENUS = (
    ("CHAMBO-STICKY-PORK", "ข้าวเหนียวหมูย่าง", "20", "rice", "อาหารจานเดียว"),
    ("CHAMBO-RICEBOX-PORK", "ข้าวกล่องหมูย่าง", "40", "rice", "อาหารจานเดียว"),
    ("CHAMBO-RICE-NAMTOK", "ข้าวหมูน้ำตก", "50", "rice", "อาหารจานเดียว"),
    ("CHAMBO-NAMTOK-PORK", "น้ำตกหมู", "80", "pork", "หมูย่างและกับข้าว"),
    ("CHAMBO-PORK-1HEED", "หมูย่าง 1 ขีด", "35", "pork", "หมูย่างและกับข้าว"),
    ("CHAMBO-PORK-3HEED", "หมูย่าง 3 ขีด", "100", "pork", "หมูย่างและกับข้าว"),
    ("CHAMBO-STICKY-RICE", "ข้าวเหนียว", "10", "side", "เพิ่มเติม"),
    ("CHAMBO-VEGSET", "ชุดผัก", "10", "side", "เพิ่มเติม"),
)

async def main():
    if os.getenv("UAT_CHAMBO_CATALOG_RECONCILE") != "1":
        raise RuntimeError("Explicit UAT reconciliation gate required")
    async with TakeawaySessionLocal() as db:
        target = (await db.execute(text("SELECT current_database(), host(inet_server_addr())"))).one()
        if target != ("takeaway_ops_db", "172.18.0.4"):
            raise RuntimeError("Refusing non-UAT database")
        refs = (await db.scalars(select(TakeawayReferenceProjection).where(
            TakeawayReferenceProjection.company_id == COMPANY,
            TakeawayReferenceProjection.aggregate_id.in_([BRANCH, BRAND]),
        ))).all()
        assert any(r.aggregate_type == "branch" and r.payload.get("code") == "BKK-01" and r.payload.get("is_active") for r in refs)
        assert any(r.aggregate_type == "brand" and r.payload.get("slug") == "chambo" and r.payload.get("is_active") for r in refs)
        allowed = []
        for index, (sku, name, price, category, category_name) in enumerate(MENUS):
            category_id = uuid.uuid5(BRAND, "approved-sale-category:" + category)
            await db.execute(insert(TakeawayCategory).values(
                id=category_id, company_id=COMPANY, brand_id=BRAND,
                code="chambo-sale-" + category, name=category_name, sort_order=index, is_active=True,
            ).on_conflict_do_nothing())
            item = await db.scalar(select(TakeawayCatalogItem).where(
                TakeawayCatalogItem.company_id == COMPANY, TakeawayCatalogItem.brand_id == BRAND,
                TakeawayCatalogItem.sku == sku,
            ))
            if item is None:
                item = TakeawayCatalogItem(id=uuid.uuid5(BRAND, sku), company_id=COMPANY, brand_id=BRAND,
                    sku=sku, name=name, price=Decimal(price), tax_rate=Decimal("0"), unit="ชุด",
                    track_stock=False, source_metadata={"source": "user-approved-uat11"})
                db.add(item)
            item.name, item.category_id, item.sort_order, item.is_active = name, category_id, index, True
            item.source_metadata = {**(item.source_metadata or {}), "is_for_sale": True,
                "product_type": "menu_item", "item_kind": "menu_item", "catalog_approval": "chambo-bkk01-uat11"}
            await db.flush()
            allowed.append(item.id)
            await db.execute(insert(TakeawayBranchCatalogItem).values(
                id=uuid.uuid5(BRANCH, sku), company_id=COMPANY, brand_id=BRAND, branch_id=BRANCH,
                catalog_item_id=item.id, price_override=Decimal(price), is_available=True,
            ).on_conflict_do_update(constraint="uq_takeaway_branch_catalog_item", set_={
                "price_override": Decimal(price), "is_available": True,
            }))
        await db.execute(update(TakeawayBranchCatalogItem).where(
            TakeawayBranchCatalogItem.company_id == COMPANY, TakeawayBranchCatalogItem.brand_id == BRAND,
            TakeawayBranchCatalogItem.branch_id == BRANCH, TakeawayBranchCatalogItem.catalog_item_id.not_in(allowed),
        ).values(is_available=False))
        await db.commit()
        print(json.dumps({"scope": "UAT/sketch-biz/chambo/BKK-01", "approved_menus": len(allowed),
            "stock_recipes_history": "unchanged", "menus": [{"sku": row[0], "name": row[1], "price": row[2]} for row in MENUS]}, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
