from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

import psycopg2
from psycopg2.extras import RealDictCursor


MAPPING_CONTRACT = "foodchainservice.takeaway-import-mapping"
SCHEMA_VERSION = "1.0.0-draft"


SECTION_RECORD_TYPES = {
    "units": "unit",
    "categories": "category",
    "items": "item",
    "recipes": "recipe",
    "replenishment_policies": "replenishment_policy",
    "stock_locations": "stock_location",
    "opening_stock": "opening_stock",
    "opening_credit": "opening_credit",
    "historical_sales": "historical_sale",
    "historical_shifts": "historical_shift",
    "historical_central_orders": "historical_central_order",
    "historical_production": "historical_production",
    "historical_transfers": "historical_transfer",
    "historical_credit_ledger": "historical_credit_ledger",
    "media_metadata": "media_metadata",
}


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _decimal(value: object, default: str = "0") -> str:
    if value is None:
        return default
    return format(Decimal(str(value)), "f")


def _utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _record(record_type: str, row: dict[str, object], data: dict[str, object]) -> dict[str, object]:
    updated = row.get("updated_at") or row.get("created_at")
    return {
        "record_type": record_type,
        "source_id": str(row["id"]),
        "source_updated_at": _utc(updated if isinstance(updated, datetime) else None),
        "data": data,
    }


def _database_url() -> str:
    value = os.getenv("CHAMBO_SOURCE_DATABASE_URL", "").strip()
    if not value:
        raise ValueError("CHAMBO_SOURCE_DATABASE_URL is required")
    return value.replace("postgresql+asyncpg://", "postgresql://", 1).replace(
        "postgresql+psycopg2://", "postgresql://", 1
    )


def _load_mapping_template(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Mapping template must be a JSON object")
    company = value.get("company")
    brand = value.get("brand")
    branches = value.get("branches")
    if not isinstance(company, dict) or not company.get("source_id") or not company.get("target_id"):
        raise ValueError("Mapping template requires company source_id and target_id")
    if not isinstance(brand, dict) or not brand.get("source_id") or not brand.get("target_id"):
        raise ValueError("Mapping template requires brand source_id and target_id")
    if brand.get("business_type") != "takeaway":
        raise ValueError("Mapped brand business_type must be takeaway")
    if not isinstance(branches, list) or not branches:
        raise ValueError("Mapping template requires at least one branch mapping")
    return value


def _fetch_all(cursor: RealDictCursor, query: str, parameters: tuple[object, ...]) -> list[dict[str, object]]:
    cursor.execute(query, parameters)
    return [dict(row) for row in cursor.fetchall()]


def _fetch_value(cursor: RealDictCursor, query: str, parameters: tuple[object, ...] = ()) -> object:
    cursor.execute(query, parameters)
    row = cursor.fetchone()
    if row is None:
        return None
    return next(iter(row.values()))


def _location_type(
    row: dict[str, object],
    *,
    central_raw_id: str | None,
    central_ready_id: str | None,
    store_location_ids: set[str],
) -> str:
    location_id = str(row["id"])
    if location_id == central_raw_id:
        return "central_raw"
    if location_id == central_ready_id:
        return "central_ready"
    if location_id in store_location_ids:
        return "store"
    marker = f"{row.get('code', '')} {row.get('name', '')}".lower()
    if "transit" in marker:
        return "transit"
    if "waste" in marker:
        return "waste"
    return "store"


def _open_operation_counts(cursor: RealDictCursor, branch_ids: list[str], brand_id: str) -> dict[str, int]:
    return {
        "cashier_shifts": int(
            _fetch_value(
                cursor,
                "SELECT count(*) FROM cashier_shifts WHERE branch_id = ANY(%s::uuid[]) AND status = 'open'",
                (branch_ids,),
            )
            or 0
        ),
        "sale_orders": int(
            _fetch_value(
                cursor,
                "SELECT count(*) FROM sale_orders WHERE branch_id = ANY(%s::uuid[]) AND status NOT IN ('completed','voided','refunded','partially_refunded','cancelled')",
                (branch_ids,),
            )
            or 0
        ),
        "central_orders": int(
            _fetch_value(
                cursor,
                "SELECT count(*) FROM central_orders WHERE brand_id = %s::uuid AND status NOT IN ('received','cancelled')",
                (brand_id,),
            )
            or 0
        ),
        "production_batches": int(
            _fetch_value(
                cursor,
                "SELECT count(*) FROM production_batches WHERE brand_id = %s::uuid AND status NOT IN ('completed','cancelled')",
                (brand_id,),
            )
            or 0
        ),
        "transfers": int(
            _fetch_value(
                cursor,
                "SELECT count(*) FROM transfer_orders WHERE (from_branch_id = ANY(%s::uuid[]) OR to_branch_id = ANY(%s::uuid[])) AND status NOT IN ('completed','cancelled','received')",
                (branch_ids, branch_ids),
            )
            or 0
        ),
        "topups": int(
            _fetch_value(
                cursor,
                "SELECT count(*) FROM credit_topup_requests WHERE brand_id = %s::uuid AND status NOT IN ('approved','rejected','cancelled')",
                (brand_id,),
            )
            or 0
        ),
        "stock_counts": int(
            _fetch_value(
                cursor,
                "SELECT count(*) FROM stock_count_sessions WHERE branch_id = ANY(%s::uuid[]) AND status NOT IN ('completed','cancelled')",
                (branch_ids,),
            )
            or 0
        ),
    }


def _extract_records(
    cursor: RealDictCursor,
    *,
    company_id: str,
    brand_id: str,
    branch_ids: list[str],
) -> dict[str, list[dict[str, object]]]:
    result = {section: [] for section in SECTION_RECORD_TYPES}

    units = _fetch_all(
        cursor,
        "SELECT id, code, name, name_en, decimal_places, is_active, created_at, updated_at FROM units WHERE company_id=%s::uuid AND deleted_at IS NULL ORDER BY code",
        (company_id,),
    )
    result["units"] = [
        _record(
            "unit",
            row,
            {
                "code": row["code"],
                "name": row["name"],
                "name_en": row.get("name_en"),
                "decimal_places": int(row.get("decimal_places") or 0),
                "is_active": bool(row.get("is_active", True)),
            },
        )
        for row in units
    ]

    categories = _fetch_all(
        cursor,
        "SELECT id, parent_id, code, name, sort_order, is_active, created_at, updated_at FROM categories WHERE company_id=%s::uuid AND deleted_at IS NULL ORDER BY sort_order, code",
        (company_id,),
    )
    result["categories"] = [
        _record(
            "category",
            row,
            {
                "code": row["code"],
                "name": row["name"],
                "parent_source_id": str(row["parent_id"]) if row.get("parent_id") else None,
                "sort_order": int(row.get("sort_order") or 0),
                "is_active": bool(row.get("is_active", True)),
            },
        )
        for row in categories
    ]

    products = _fetch_all(
        cursor,
        """
        SELECT p.*, u.code AS unit_code
        FROM products p
        JOIN units u ON u.id=p.unit_id
        WHERE p.company_id=%s::uuid AND p.deleted_at IS NULL AND (p.brand_id=%s::uuid OR p.brand_id IS NULL)
        ORDER BY p.sku
        """,
        (company_id, brand_id),
    )
    product_ids = [str(row["id"]) for row in products]
    result["items"] = [
        _record(
            "item",
            row,
            {
                "sku": row["sku"],
                "barcode": row.get("barcode"),
                "name": row["name"],
                "category_source_id": str(row["category_id"]) if row.get("category_id") else None,
                "unit_code": row["unit_code"],
                "product_type": row.get("product_type") or "stock",
                "inventory_role": row.get("inventory_role") or "not_stocked",
                "brand_scope": "shared" if row.get("brand_id") is None else "brand",
                "cost_price": _decimal(row.get("cost_price")),
                "selling_price": _decimal(row.get("selling_price")),
                "vat_type": row.get("vat_type") or "exclusive",
                "vat_rate": _decimal(row.get("vat_rate"), "7"),
                "image_media_source_id": None,
                "is_active": bool(row.get("is_active", True)),
                "is_for_sale": bool(row.get("is_for_sale", False)),
                "is_for_purchase": bool(row.get("is_for_purchase", False)),
            },
        )
        for row in products
    ]

    recipes = _fetch_all(
        cursor,
        """
        SELECT r.*, p.sku AS output_sku, u.code AS yield_unit_code
        FROM recipes r
        JOIN products p ON p.id=r.product_id
        JOIN units u ON u.id=p.unit_id
        WHERE r.company_id=%s::uuid AND (r.brand_id=%s::uuid OR r.brand_id IS NULL)
        ORDER BY r.created_at, r.id
        """,
        (company_id, brand_id),
    )
    for row in recipes:
        ingredients = _fetch_all(
            cursor,
            """
            SELECT ri.*, p.sku, coalesce(u.code, ri.unit) AS unit_code
            FROM recipe_ingredients ri
            JOIN products p ON p.id=ri.ingredient_id
            LEFT JOIN units u ON u.id=p.unit_id
            WHERE ri.recipe_id=%s::uuid
            ORDER BY ri.sort_order, ri.id
            """,
            (str(row["id"]),),
        )
        result["recipes"].append(
            _record(
                "recipe",
                row,
                {
                    "output_item_source_id": str(row["product_id"]),
                    "output_sku": row["output_sku"],
                    "branch_source_id": str(row["branch_id"]) if row.get("branch_id") else None,
                    "recipe_type": row.get("recipe_type") or "sale_recipe",
                    "version_no": int(row.get("version_no") or 1),
                    "effective_from": row["effective_from"].isoformat() if row.get("effective_from") else None,
                    "effective_to": row["effective_to"].isoformat() if row.get("effective_to") else None,
                    "name": row["name"],
                    "yield_qty": _decimal(row.get("yield_qty"), "1"),
                    "yield_unit_code": row["yield_unit_code"],
                    "loss_percent": _decimal(row.get("loss_percent")),
                    "is_active": bool(row.get("is_active", True)),
                    "ingredients": [
                        {
                            "source_id": str(item["id"]),
                            "item_source_id": str(item["ingredient_id"]),
                            "sku": item["sku"],
                            "quantity": _decimal(item["quantity"]),
                            "unit_code": item["unit_code"],
                            "sort_order": int(item.get("sort_order") or 0),
                        }
                        for item in ingredients
                    ],
                },
            )
        )

    policies = _fetch_all(
        cursor,
        """
        SELECT p.*, i.sku
        FROM branch_replenishment_policies p
        JOIN products i ON i.id=p.product_id
        WHERE p.company_id=%s::uuid AND p.brand_id=%s::uuid AND p.branch_id=ANY(%s::uuid[])
        ORDER BY p.branch_id, i.sku
        """,
        (company_id, brand_id, branch_ids),
    )
    result["replenishment_policies"] = [
        _record(
            "replenishment_policy",
            row,
            {
                "branch_source_id": str(row["branch_id"]),
                "item_source_id": str(row["product_id"]),
                "sku": row["sku"],
                "is_enabled": bool(row.get("is_enabled", True)),
                "safety_stock_percent": _decimal(row.get("safety_stock_percent")),
                "safety_stock_qty": _decimal(row.get("safety_stock_qty")),
                "pack_size": _decimal(row.get("pack_size"), "1"),
                "lead_time_days": int(row.get("lead_time_days") or 1),
                "forecast_method": row.get("forecast_method") or "auto",
                "minimum_order_qty": _decimal(row.get("minimum_order_qty")),
            },
        )
        for row in policies
    ]

    brand = _fetch_all(
        cursor,
        "SELECT central_location_id, central_ready_location_id FROM brands WHERE id=%s::uuid AND company_id=%s::uuid",
        (brand_id, company_id),
    )[0]
    store_location_ids = {
        str(row["store_location_id"])
        for row in _fetch_all(
            cursor,
            "SELECT store_location_id FROM brand_branches WHERE brand_id=%s::uuid AND branch_id=ANY(%s::uuid[]) AND store_location_id IS NOT NULL",
            (brand_id, branch_ids),
        )
    }
    locations = _fetch_all(
        cursor,
        "SELECT id, branch_id, code, name, is_active, created_at, updated_at FROM stock_locations WHERE company_id=%s::uuid AND branch_id=ANY(%s::uuid[]) AND deleted_at IS NULL ORDER BY code,id",
        (company_id, branch_ids),
    )
    location_ids = [str(row["id"]) for row in locations]
    central_raw_id = str(brand["central_location_id"]) if brand.get("central_location_id") else None
    central_ready_id = str(brand["central_ready_location_id"]) if brand.get("central_ready_location_id") else None
    result["stock_locations"] = [
        _record(
            "stock_location",
            row,
            {
                "branch_source_id": str(row["branch_id"]),
                "code": row["code"],
                "name": row["name"],
                "location_type": _location_type(
                    row,
                    central_raw_id=central_raw_id,
                    central_ready_id=central_ready_id,
                    store_location_ids=store_location_ids,
                ),
                "is_active": bool(row.get("is_active", True)),
            },
        )
        for row in locations
    ]

    balances = _fetch_all(
        cursor,
        """
        SELECT b.*, p.sku, u.code AS unit_code
        FROM stock_balances b
        JOIN products p ON p.id=b.product_id
        JOIN units u ON u.id=p.unit_id
        WHERE b.company_id=%s::uuid AND b.branch_id=ANY(%s::uuid[])
          AND b.location_id=ANY(%s::uuid[]) AND b.product_id=ANY(%s::uuid[])
        ORDER BY b.branch_id,b.location_id,p.sku,b.id
        """,
        (company_id, branch_ids, location_ids, product_ids),
    )
    result["opening_stock"] = [
        _record(
            "opening_stock",
            row,
            {
                "branch_source_id": str(row["branch_id"]),
                "location_source_id": str(row["location_id"]),
                "item_source_id": str(row["product_id"]),
                "sku": row["sku"],
                "unit_code": row["unit_code"],
                "lot_code": "OPENING",
                "expiry_date": None,
                "qty_on_hand": _decimal(row.get("qty_on_hand")),
                "qty_reserved": _decimal(row.get("qty_reserved")),
                "cost_per_unit": _decimal(row.get("cost_per_unit")),
                "as_of": _utc(row.get("last_movement_at") if isinstance(row.get("last_movement_at"), datetime) else row.get("updated_at")),
                "proof_reference": f"stock_balance:{row['id']}",
            },
        )
        for row in balances
    ]

    credits = _fetch_all(
        cursor,
        "SELECT * FROM credit_accounts WHERE company_id=%s::uuid AND brand_id=%s::uuid AND branch_id=ANY(%s::uuid[]) ORDER BY branch_id,id",
        (company_id, brand_id, branch_ids),
    )
    result["opening_credit"] = [
        _record(
            "opening_credit",
            row,
            {
                "branch_source_id": str(row["branch_id"]),
                "currency": "THB",
                "credit_limit": _decimal(row.get("credit_limit")),
                "balance": _decimal(row.get("balance")),
                "reserved_amount": _decimal(row.get("reserved_amount")),
                "as_of": _utc(row.get("updated_at") if isinstance(row.get("updated_at"), datetime) else None),
                "proof_reference": f"credit_account:{row['id']}",
            },
        )
        for row in credits
    ]

    sales = _fetch_all(
        cursor,
        "SELECT * FROM sale_orders WHERE company_id=%s::uuid AND branch_id=ANY(%s::uuid[]) ORDER BY business_at,id",
        (company_id, branch_ids),
    )
    for row in sales:
        items = _fetch_all(
            cursor,
            "SELECT id,product_id,sku,product_name,qty,unit_price,discount_amount,vat_amount,subtotal FROM sale_order_items WHERE order_id=%s::uuid ORDER BY created_at,id",
            (str(row["id"]),),
        )
        payments = _fetch_all(
            cursor,
            "SELECT payment_method,amount,paid_at FROM payments WHERE order_id=%s::uuid ORDER BY paid_at,id",
            (str(row["id"]),),
        )
        result["historical_sales"].append(
            _record(
                "historical_sale",
                row,
                {
                    "branch_source_id": str(row["branch_id"]),
                    "legacy_document_number": row["order_number"],
                    "business_at": _utc(row.get("business_at")),
                    "status": row["status"],
                    "subtotal": _decimal(row.get("subtotal")),
                    "discount_amount": _decimal(row.get("discount_amount")),
                    "vat_amount": _decimal(row.get("vat_amount")),
                    "total_amount": _decimal(row.get("total_amount")),
                    "paid_amount": _decimal(row.get("paid_amount")),
                    "refund_amount": _decimal(row.get("refund_amount")),
                    "items": [
                        {
                            "source_id": str(item["id"]),
                            "item_source_id": str(item["product_id"]),
                            "sku": item["sku"],
                            "name": item["product_name"],
                            "qty": _decimal(item["qty"]),
                            "unit_price": _decimal(item["unit_price"]),
                            "discount_amount": _decimal(item["discount_amount"]),
                            "vat_amount": _decimal(item["vat_amount"]),
                            "subtotal": _decimal(item["subtotal"]),
                        }
                        for item in items
                    ],
                    "payments": [
                        {
                            "payment_method": payment["payment_method"],
                            "amount": _decimal(payment["amount"]),
                            "paid_at": _utc(payment["paid_at"]),
                        }
                        for payment in payments
                    ],
                },
            )
        )

    shifts = _fetch_all(
        cursor,
        "SELECT * FROM cashier_shifts WHERE company_id=%s::uuid AND branch_id=ANY(%s::uuid[]) ORDER BY opened_at,id",
        (company_id, branch_ids),
    )
    result["historical_shifts"] = [
        _record(
            "historical_shift",
            row,
            {
                "branch_source_id": str(row["branch_id"]),
                "shift_number": row["shift_number"],
                "status": row["status"],
                "opened_at": _utc(row.get("opened_at")),
                "closed_at": _utc(row.get("closed_at")),
                "opening_cash": _decimal(row.get("opening_cash")),
                "closing_cash": _decimal(row.get("closing_cash")),
                "expected_cash": _decimal(row.get("expected_cash")),
                "cash_difference": _decimal(row.get("cash_difference")),
                "total_sales": _decimal(row.get("total_sales")),
                "total_orders": int(row.get("total_orders") or 0),
                "total_voids": int(row.get("total_voids") or 0),
            },
        )
        for row in shifts
    ]

    central_orders = _fetch_all(
        cursor,
        "SELECT * FROM central_orders WHERE company_id=%s::uuid AND brand_id=%s::uuid AND branch_id=ANY(%s::uuid[]) ORDER BY created_at,id",
        (company_id, brand_id, branch_ids),
    )
    for row in central_orders:
        items = _fetch_all(
            cursor,
            "SELECT id,product_id,sku,product_name,unit,unit_cost,requested_qty,approved_qty,shipped_qty,received_qty,requested_amount,approved_amount,shipped_amount,source FROM central_order_items WHERE order_id=%s::uuid ORDER BY sort_order,id",
            (str(row["id"]),),
        )
        result["historical_central_orders"].append(
            _record(
                "historical_central_order",
                row,
                {
                    "branch_source_id": str(row["branch_id"]),
                    "order_number": row["order_number"],
                    "business_date": row["business_date"],
                    "status": row["status"],
                    "credit_reserved_amount": _decimal(row.get("credit_reserved_amount")),
                    "credit_captured_amount": _decimal(row.get("credit_captured_amount")),
                    "credit_released_amount": _decimal(row.get("credit_released_amount")),
                    "items": [
                        {
                            "source_id": str(item["id"]),
                            "item_source_id": str(item["product_id"]) if item.get("product_id") else None,
                            "sku": item["sku"],
                            "name": item["product_name"],
                            "unit": item["unit"],
                            "unit_cost": _decimal(item["unit_cost"]),
                            "requested_qty": _decimal(item["requested_qty"]),
                            "approved_qty": _decimal(item["approved_qty"]),
                            "shipped_qty": _decimal(item["shipped_qty"]),
                            "received_qty": _decimal(item["received_qty"]),
                            "requested_amount": _decimal(item["requested_amount"]),
                            "approved_amount": _decimal(item["approved_amount"]),
                            "shipped_amount": _decimal(item["shipped_amount"]),
                            "source": item["source"],
                        }
                        for item in items
                    ],
                },
            )
        )

    production = _fetch_all(
        cursor,
        "SELECT * FROM production_batches WHERE company_id=%s::uuid AND brand_id=%s::uuid ORDER BY created_at,id",
        (company_id, brand_id),
    )
    result["historical_production"] = [
        _record(
            "historical_production",
            row,
            {
                "branch_source_id": None,
                "batch_number": row["batch_number"],
                "planned_at": _utc(row.get("planned_at")),
                "status": row["status"],
            },
        )
        for row in production
    ]

    transfers = _fetch_all(
        cursor,
        "SELECT * FROM transfer_orders WHERE company_id=%s::uuid AND (from_branch_id=ANY(%s::uuid[]) OR to_branch_id=ANY(%s::uuid[])) ORDER BY created_at,id",
        (company_id, branch_ids, branch_ids),
    )
    result["historical_transfers"] = [
        _record(
            "historical_transfer",
            row,
            {
                "branch_source_id": str(row["to_branch_id"]),
                "transfer_number": row["to_number"],
                "status": row["status"],
                "occurred_at": _utc(row.get("created_at")),
            },
        )
        for row in transfers
    ]

    ledgers = _fetch_all(
        cursor,
        "SELECT * FROM credit_ledgers WHERE company_id=%s::uuid AND brand_id=%s::uuid AND branch_id=ANY(%s::uuid[]) ORDER BY created_at,id",
        (company_id, brand_id, branch_ids),
    )
    result["historical_credit_ledger"] = [
        _record(
            "historical_credit_ledger",
            row,
            {
                "branch_source_id": str(row["branch_id"]),
                "legacy_document_number": row.get("reference_id") or str(row["id"]),
                "entry_type": row["entry_type"],
                "amount": _decimal(row.get("amount")),
                "balance_after": _decimal(row.get("balance_after")),
                "reserved_after": _decimal(row.get("reserved_after")),
                "reference_type": row.get("reference_type"),
                "occurred_at": _utc(row.get("created_at")),
            },
        )
        for row in ledgers
    ]
    return result


def create_snapshot(
    *,
    output: Path,
    mapping_template_path: Path,
    repository_commit: str,
) -> dict[str, object]:
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing snapshot directory")
    if len(repository_commit) != 40 or any(character not in "0123456789abcdef" for character in repository_commit.lower()):
        raise ValueError("Source repository commit must be a 40-character hexadecimal SHA")
    template = _load_mapping_template(mapping_template_path)
    company = template["company"]
    brand = template["brand"]
    branches = template["branches"]
    assert isinstance(company, dict) and isinstance(brand, dict) and isinstance(branches, list)
    company_id = str(company["source_id"])
    brand_id = str(brand["source_id"])
    branch_ids = [str(row["source_id"]) for row in branches if isinstance(row, dict)]
    export_id = str(uuid.uuid4())
    mapping = {
        "contract": MAPPING_CONTRACT,
        "schema_version": SCHEMA_VERSION,
        "mapping_id": str(uuid.uuid4()),
        "export_id": export_id,
        "company": company,
        "brand": brand,
        "branches": branches,
        "locations": template.get("locations", []),
    }
    connection = psycopg2.connect(_database_url(), cursor_factory=RealDictCursor)
    try:
        connection.set_session(readonly=True, autocommit=False, isolation_level="REPEATABLE READ")
        with connection.cursor() as cursor:
            read_only = _fetch_value(cursor, "SHOW transaction_read_only")
            if str(read_only).lower() != "on":
                raise RuntimeError("Source transaction is not read-only")
            cutoff = _fetch_value(cursor, "SELECT transaction_timestamp()")
            migration_head = _fetch_value(cursor, "SELECT version_num FROM alembic_version")
            company_count = int(
                _fetch_value(cursor, "SELECT count(*) FROM companies WHERE id=%s::uuid", (company_id,)) or 0
            )
            brand_count = int(
                _fetch_value(
                    cursor,
                    "SELECT count(*) FROM brands WHERE id=%s::uuid AND company_id=%s::uuid",
                    (brand_id, company_id),
                )
                or 0
            )
            mapped_branch_count = int(
                _fetch_value(
                    cursor,
                    "SELECT count(*) FROM brand_branches WHERE company_id=%s::uuid AND brand_id=%s::uuid AND branch_id=ANY(%s::uuid[]) AND is_active",
                    (company_id, brand_id, branch_ids),
                )
                or 0
            )
            if company_count != 1 or brand_count != 1 or mapped_branch_count != len(branch_ids):
                raise ValueError("Source company, brand or branch mapping does not match the approved scope")
            open_operations = _open_operation_counts(cursor, branch_ids, brand_id)
            if any(open_operations.values()):
                raise ValueError(f"Source has open operations: {open_operations}")
            records = _extract_records(
                cursor,
                company_id=company_id,
                brand_id=brand_id,
                branch_ids=branch_ids,
            )
            connection.rollback()
    finally:
        connection.close()

    output.mkdir(mode=0o700, parents=True)
    (output / "data").mkdir(mode=0o700)
    try:
        (output / "mapping.json").write_text(_canonical(mapping) + "\n", encoding="utf-8")
        counts: dict[str, int] = {}
        for section, rows in records.items():
            counts[section] = len(rows)
            path = output / "data" / f"{section.replace('_', '-')}.ndjson"
            path.write_text("".join(_canonical(row) + "\n" for row in rows), encoding="utf-8")
        cutoff_at = _utc(cutoff if isinstance(cutoff, datetime) else None)
        snapshot_id = f"chambo-{str(cutoff_at).replace(':', '').replace('-', '')}-{export_id[:8]}"
        summary = {
            "export_id": export_id,
            "cutoff_at": cutoff_at,
            "source": {
                "system": "erp-pos-run",
                "repository": "chaiyanutaiagent/erp-pos-run",
                "repository_commit": repository_commit,
                "migration_head": str(migration_head),
                "environment": "approved_snapshot",
                "snapshot_id": snapshot_id,
                "read_only": True,
            },
            "scope": {
                "company_source_id": company_id,
                "brand_source_id": brand_id,
                "branch_source_ids": branch_ids,
                "target_company_id": str(company["target_id"]),
                "target_brand_id": str(brand["target_id"]),
            },
            "omitted_sections": [],
            "cutover_controls": {
                "open_operations": open_operations,
                "target_side_effects_disabled": True,
            },
            "record_totals": counts,
        }
        (output / "source-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {
            "status": "snapshot_created",
            "snapshot": str(output),
            "snapshot_id": snapshot_id,
            "cutoff_at": cutoff_at,
            "record_totals": counts,
            "open_operations": open_operations,
        }
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a normalized read-only Chambo snapshot for the signed Takeaway exporter"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mapping-template", type=Path, required=True)
    parser.add_argument("--repository-commit", required=True)
    args = parser.parse_args()
    try:
        result = create_snapshot(
            output=args.output,
            mapping_template_path=args.mapping_template,
            repository_commit=args.repository_commit.lower(),
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, psycopg2.Error) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
