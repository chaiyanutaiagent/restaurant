from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import takeaway_engine
from app.dependencies import TokenData
from app.models.takeaway import (
    TakeawayCreditAccount,
    TakeawayHistoricalArchive,
    TakeawayImportRecord,
    TakeawayOperationalOutbox,
    TakeawayRecipe,
    TakeawayRecipeIngredient,
    TakeawayReferenceProjection,
    TakeawayReplenishmentPolicy,
    TakeawayStockBalance,
    TakeawayStockLocation,
    TakeawayUnit,
)
from app.services.takeaway_import_service import (
    CONTRACT,
    MAPPING_CONTRACT,
    SCHEMA_VERSION,
    TakeawayImportService,
    canonical_record_hash,
)


def projection(aggregate_id: uuid.UUID, company_id: uuid.UUID) -> TakeawayReferenceProjection:
    payload = {
        "id": str(aggregate_id),
        "company_id": str(company_id),
        "name": "Synthetic Takeaway",
        "business_type": "takeaway",
        "is_active": True,
    }
    return TakeawayReferenceProjection(
        aggregate_type="brand",
        aggregate_id=aggregate_id,
        company_id=company_id,
        source_updated_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        payload=payload,
        source_digest=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
    )


def sealed(record_type: str, source_id: uuid.UUID, data: dict[str, object]) -> dict[str, object]:
    return {
        "record_type": record_type,
        "source_id": str(source_id),
        "source_updated_at": "2026-09-11T00:00:00Z",
        "source_hash": canonical_record_hash(record_type, str(source_id), data),
        "data": data,
    }


async def run() -> None:
    if takeaway_engine is None:
        raise RuntimeError("TAKEAWAY_DATABASE_URL is required")
    company_id, brand_id, target_branch_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    source_branch_id, location_id = uuid.uuid4(), uuid.uuid4()
    unit_id, category_id, raw_id, output_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    recipe_id, policy_id, stock_id, credit_id, history_id = (uuid.uuid4() for _ in range(5))
    export_id = uuid.uuid4()

    unit = {"code": "KG", "name": "กิโลกรัม", "name_en": "Kilogram", "decimal_places": 3, "is_active": True}
    category = {"code": "ready", "name": "สินค้าพร้อมขาย", "parent_source_id": None, "sort_order": 1, "is_active": True}
    raw = {
        "sku": f"RAW-{str(raw_id)[:8]}", "barcode": None, "name": "หมูวัตถุดิบร่วม",
        "category_source_id": str(category_id), "unit_code": "KG", "product_type": "stock",
        "inventory_role": "central_raw", "brand_scope": "shared", "cost_price": "100.00",
        "selling_price": "0.00", "vat_type": "exclusive", "vat_rate": "7.00",
        "image_media_source_id": None, "is_active": True, "is_for_sale": False, "is_for_purchase": True,
    }
    output = {
        "sku": f"OUT-{str(output_id)[:8]}", "barcode": None, "name": "หมูแดดเดียวพร้อมขาย",
        "category_source_id": str(category_id), "unit_code": "KG", "product_type": "stock",
        "inventory_role": "central_ready", "brand_scope": "brand", "cost_price": "140.00",
        "selling_price": "199.00", "vat_type": "exclusive", "vat_rate": "7.00",
        "image_media_source_id": None, "is_active": True, "is_for_sale": True, "is_for_purchase": False,
    }
    location = {
        "branch_source_id": str(source_branch_id), "code": f"CENTRAL-{str(location_id)[:8]}",
        "name": "คลังกลางทดสอบ", "location_type": "central_raw", "is_active": True,
    }
    recipe = {
        "output_item_source_id": str(output_id), "output_sku": output["sku"], "branch_source_id": None,
        "recipe_type": "production_recipe", "version_no": 1, "effective_from": "2026-09-11",
        "effective_to": None, "name": "สูตรหมูแดดเดียว", "yield_qty": "1.00", "yield_unit_code": "KG",
        "loss_percent": "5.00", "is_active": True,
        "ingredients": [{"source_id": str(uuid.uuid4()), "item_source_id": str(raw_id), "sku": raw["sku"], "quantity": "1.05", "unit_code": "KG", "sort_order": 0}],
    }
    policy = {
        "branch_source_id": str(source_branch_id), "item_source_id": str(output_id), "sku": output["sku"],
        "is_enabled": True, "safety_stock_percent": "10.00", "safety_stock_qty": "5.00",
        "pack_size": "1.00", "lead_time_days": 1, "forecast_method": "auto", "minimum_order_qty": "2.00",
    }
    opening_stock = {
        "branch_source_id": str(source_branch_id), "location_source_id": str(location_id),
        "item_source_id": str(raw_id), "sku": raw["sku"], "unit_code": "KG", "lot_code": "OPEN",
        "expiry_date": None, "qty_on_hand": "50.00", "qty_reserved": "2.00", "cost_per_unit": "100.00",
        "as_of": "2026-09-11T00:00:00Z", "proof_reference": "synthetic-opening-stock",
    }
    opening_credit = {
        "branch_source_id": str(source_branch_id), "currency": "THB", "credit_limit": "10000.00",
        "balance": "1500.00", "reserved_amount": "0.00", "as_of": "2026-09-11T00:00:00Z",
        "proof_reference": "synthetic-opening-credit",
    }
    history = {
        "branch_source_id": str(source_branch_id), "legacy_document_number": "LEGACY-SALE-001",
        "business_at": "2026-09-10T12:00:00Z", "total_amount": "199.00",
    }
    records = [
        sealed("historical_sale", history_id, history),
        sealed("opening_credit", credit_id, opening_credit),
        sealed("opening_stock", stock_id, opening_stock),
        sealed("replenishment_policy", policy_id, policy),
        sealed("recipe", recipe_id, recipe),
        sealed("stock_location", location_id, location),
        sealed("item", output_id, output),
        sealed("item", raw_id, raw),
        sealed("category", category_id, category),
        sealed("unit", unit_id, unit),
    ]
    manifest = {
        "contract": CONTRACT, "schema_version": SCHEMA_VERSION, "export_id": str(export_id),
        "generated_at": "2026-09-11T00:00:00Z", "cutoff_at": "2026-09-11T00:00:00Z",
        "timezone": "Asia/Bangkok",
        "source": {"system": "erp-pos-run", "repository": "chaiyanutaiagent/erp-pos-run", "repository_commit": "1" * 40,
                   "migration_head": "synthetic", "environment": "synthetic", "snapshot_id": "synthetic-full-import", "read_only": True},
        "scope": {}, "mapping": {"path": "mapping.json", "sha256": "0" * 64}, "files": [],
        "omitted_sections": [],
        "record_totals": {"units": 1, "categories": 1, "items": 2, "stock_locations": 1, "recipes": 1,
                          "replenishment_policies": 1, "opening_stock": 1, "opening_credit": 1, "historical_sales": 1},
        "security_attestation": {"forbidden_field_findings": 0, "unapproved_pii_findings": 0, "unsafe_media_findings": 0, "scanner_version": "synthetic"},
    }
    mapping = {
        "contract": MAPPING_CONTRACT, "schema_version": SCHEMA_VERSION, "mapping_id": str(uuid.uuid4()),
        "export_id": str(export_id), "company": {"source_id": str(uuid.uuid4()), "target_id": str(company_id)},
        "brand": {"source_id": str(uuid.uuid4()), "target_id": str(brand_id), "business_type": "takeaway"},
        "branches": [{"source_id": str(source_branch_id), "target_id": str(target_branch_id)}],
        "locations": [{"source_id": str(location_id), "target_id": str(location_id)}],
    }
    current = TokenData(user_id=uuid.uuid4(), company_id=company_id, branch_id=None, brand_id=brand_id,
                        business_type="takeaway", target_database="takeaway", permissions=["*"], scope_types=["company"])

    async with takeaway_engine.connect() as connection:
        outer = await connection.begin()
        db = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            db.add(projection(brand_id, company_id))
            await db.flush()
            service = TakeawayImportService(db, current)
            outbox_before = int(await db.scalar(select(func.count()).select_from(TakeawayOperationalOutbox)) or 0)
            batch, replayed = await service.apply_synthetic(manifest=manifest, mapping=mapping, records=records)
            replay_batch, replayed_second = await service.apply_synthetic(manifest=manifest, mapping=mapping, records=records)
            assert not replayed and replayed_second and replay_batch.id == batch.id
            assert int(await db.scalar(select(func.count()).select_from(TakeawayImportRecord).where(TakeawayImportRecord.batch_id == batch.id)) or 0) == len(records)
            assert int(await db.scalar(select(func.count()).select_from(TakeawayUnit).where(TakeawayUnit.company_id == company_id)) or 0) == 1
            assert int(await db.scalar(select(func.count()).select_from(TakeawayStockLocation).where(TakeawayStockLocation.company_id == company_id)) or 0) == 1
            assert int(await db.scalar(select(func.count()).select_from(TakeawayRecipe).where(TakeawayRecipe.company_id == company_id)) or 0) == 1
            assert int(await db.scalar(select(func.count()).select_from(TakeawayRecipeIngredient)) or 0) >= 1
            assert int(await db.scalar(select(func.count()).select_from(TakeawayReplenishmentPolicy).where(TakeawayReplenishmentPolicy.company_id == company_id)) or 0) == 1
            balance = await db.scalar(select(TakeawayStockBalance).where(TakeawayStockBalance.company_id == company_id))
            credit = await db.scalar(select(TakeawayCreditAccount).where(TakeawayCreditAccount.company_id == company_id))
            archive = await db.scalar(select(TakeawayHistoricalArchive).where(TakeawayHistoricalArchive.import_batch_id == batch.id))
            assert balance and balance.on_hand_qty == Decimal("50.0000") and balance.reserved_qty == Decimal("2.0000")
            assert credit and credit.credit_limit == Decimal("10000.00") and credit.balance == Decimal("1500.00")
            assert archive and archive.document_number == "LEGACY-SALE-001"
            outbox_after = int(await db.scalar(select(func.count()).select_from(TakeawayOperationalOutbox)) or 0)
            assert outbox_after == outbox_before
            print(json.dumps({"status": "ok", "records": len(records), "idempotent_replay": replayed_second,
                              "opening_stock": str(balance.on_hand_qty), "opening_credit": str(credit.balance),
                              "historical_side_effects": outbox_after - outbox_before}, sort_keys=True))
        finally:
            await db.close()
            await outer.rollback()


if __name__ == "__main__":
    asyncio.run(run())
