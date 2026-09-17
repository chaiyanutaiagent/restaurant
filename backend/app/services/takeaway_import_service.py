from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import base64
import binascii
import hashlib
import json
import re
from typing import Any
import uuid

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TokenData
from app.models.takeaway import (
    TakeawayCatalogItem,
    TakeawayCategory,
    TakeawayCreditAccount,
    TakeawayCreditEntry,
    TakeawayCutoverRun,
    TakeawayHistoricalArchive,
    TakeawayImportBatch,
    TakeawayImportRecord,
    TakeawayRecipe,
    TakeawayRecipeIngredient,
    TakeawayReferenceProjection,
    TakeawayReplenishmentPolicy,
    TakeawayStockLocation,
    TakeawayUnit,
)
from app.services.takeaway_service import TakeawayService
CONTRACT = "foodchainservice.takeaway-import"
MAPPING_CONTRACT = "foodchainservice.takeaway-import-mapping"
SCHEMA_VERSION = "1.0.0-draft"
RECORD_SECTION = {
    "unit": "units",
    "category": "categories",
    "item": "items",
    "recipe": "recipes",
    "replenishment_policy": "replenishment_policies",
    "stock_location": "stock_locations",
    "opening_stock": "opening_stock",
    "opening_credit": "opening_credit",
    "historical_sale": "historical_sales",
    "historical_shift": "historical_shifts",
    "historical_central_order": "historical_central_orders",
    "historical_production": "historical_production",
    "historical_transfer": "historical_transfers",
    "historical_credit_ledger": "historical_credit_ledger",
    "media_metadata": "media_metadata",
}
HISTORICAL_TYPES = {value for value in RECORD_SECTION if value.startswith("historical_")}
FORBIDDEN_KEY_FRAGMENTS = (
    "password",
    "pin_hash",
    "access_token",
    "refresh_token",
    "session_token",
    "device_token",
    "pairing_token",
    "credential",
    "api_key",
    "private_key",
    "database_url",
)
UNAPPROVED_PII_KEYS = {"customer_name", "customer_phone", "customer_tax_id", "card_number"}
FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"postgres(?:ql)?(?:\+\w+)?://", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)
DECIMAL_FIELD_FRAGMENTS = (
    "amount",
    "price",
    "qty",
    "quantity",
    "cost",
    "balance",
    "reserved",
    "limit",
    "factor",
    "percent",
    "yield",
)
DECIMAL_EXEMPT_KEYS = {
    "decimal_places",
    "lead_time_days",
    "sort_order",
    "version_no",
    "yield_unit_code",
}


@dataclass(frozen=True)
class ImportValidationReport:
    status: str
    manifest_digest: str
    mapping_digest: str
    total_records: int
    accepted_records: int
    rejected_records: int
    section_counts: dict[str, int]
    historical_records: int
    side_effects_planned_for_history: int
    findings: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "manifest_digest": self.manifest_digest,
            "mapping_digest": self.mapping_digest,
            "total_records": self.total_records,
            "accepted_records": self.accepted_records,
            "rejected_records": self.rejected_records,
            "section_counts": self.section_counts,
            "historical_records": self.historical_records,
            "side_effects_planned_for_history": self.side_effects_planned_for_history,
            "findings": list(self.findings),
        }


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_record_hash(record_type: str, source_id: str, data: dict[str, object]) -> str:
    return digest_json(
        {"record_type": record_type, "source_id": source_id, "data": data}
    )


def verify_takeaway_manifest_seal(
    manifest: dict[str, object],
    trusted_public_keys: dict[str, str],
) -> tuple[bool, str]:
    seal = manifest.get("seal")
    if not isinstance(seal, dict):
        return False, "manifest_seal_required"
    if seal.get("algorithm") != "Ed25519":
        return False, "manifest_seal_algorithm"
    key_id = seal.get("key_id")
    signature = seal.get("signature")
    if not isinstance(key_id, str) or key_id not in trusted_public_keys:
        return False, "manifest_seal_key_untrusted"
    if not isinstance(signature, str):
        return False, "manifest_seal_signature_required"
    payload = dict(manifest)
    payload.pop("seal", None)
    try:
        public_key = serialization.load_pem_public_key(
            trusted_public_keys[key_id].encode("utf-8")
        )
        if not isinstance(public_key, Ed25519PublicKey):
            return False, "manifest_seal_key_type"
        public_key.verify(
            base64.b64decode(signature, validate=True),
            canonical_json(payload).encode("utf-8"),
        )
    except (ValueError, TypeError, binascii.Error, InvalidSignature):
        return False, "manifest_seal_invalid"
    return True, "verified"


def takeaway_import_control_totals(
    records: list[dict[str, object]],
) -> dict[str, str]:
    totals: dict[str, Decimal] = {
        "opening_stock_on_hand": Decimal("0"),
        "opening_stock_reserved": Decimal("0"),
        "opening_stock_value": Decimal("0"),
        "opening_credit_balance": Decimal("0"),
        "historical_sales_total": Decimal("0"),
    }
    for record in records:
        record_type = record.get("record_type")
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        try:
            if record_type == "opening_stock":
                quantity = Decimal(str(data.get("qty_on_hand", "0")))
                totals["opening_stock_on_hand"] += quantity
                totals["opening_stock_reserved"] += Decimal(
                    str(data.get("qty_reserved", "0"))
                )
                totals["opening_stock_value"] += quantity * Decimal(
                    str(data.get("cost_per_unit", "0"))
                )
            elif record_type == "opening_credit":
                totals["opening_credit_balance"] += Decimal(
                    str(data.get("balance", "0"))
                )
            elif record_type == "historical_sale":
                totals["historical_sales_total"] += Decimal(
                    str(data.get("total_amount", data.get("total", "0")))
                )
        except InvalidOperation:
            continue
    return {key: format(value, "f") for key, value in totals.items()}


def build_takeaway_cutover_preview(
    *,
    manifest: dict[str, object],
    mapping: dict[str, object],
    records: list[dict[str, object]],
    expected_company_id: uuid.UUID,
    expected_brand_id: uuid.UUID | None,
    trusted_public_keys: dict[str, str],
) -> dict[str, object]:
    report = validate_takeaway_import_package(
        manifest=manifest,
        mapping=mapping,
        records=records,
        expected_company_id=expected_company_id,
        expected_brand_id=expected_brand_id,
    )
    blockers = list(report.findings)
    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("environment") != "approved_snapshot":
        blockers.append({"code": "approved_snapshot_required", "path": "manifest.source.environment"})
    seal_verified, seal_status = verify_takeaway_manifest_seal(
        manifest, trusted_public_keys
    )
    if not seal_verified:
        blockers.append({"code": seal_status, "path": "manifest.seal"})
    controls = manifest.get("cutover_controls")
    if not isinstance(controls, dict):
        blockers.append({"code": "cutover_controls_required", "path": "manifest.cutover_controls"})
        controls = {}
    open_operations = controls.get("open_operations")
    if not isinstance(open_operations, dict):
        blockers.append({"code": "open_operations_required", "path": "manifest.cutover_controls.open_operations"})
        open_operations = {}
    for operation, count in sorted(open_operations.items()):
        if isinstance(count, bool) or not isinstance(count, int) or count != 0:
            blockers.append({"code": "open_operation_blocker", "path": f"manifest.cutover_controls.open_operations.{operation}", "count": count})
    if controls.get("target_side_effects_disabled") is not True:
        blockers.append({"code": "target_side_effects_must_be_disabled", "path": "manifest.cutover_controls.target_side_effects_disabled"})
    preview_core: dict[str, object] = {
        "manifest_digest": report.manifest_digest,
        "mapping_digest": report.mapping_digest,
        "total_records": report.total_records,
        "section_counts": report.section_counts,
        "control_totals": takeaway_import_control_totals(records),
        "seal_status": seal_status,
        "source_snapshot": source.get("snapshot_id") if isinstance(source, dict) else None,
        "blockers": blockers,
    }
    return {
        **preview_core,
        "ready": not blockers,
        "preview_digest": digest_json(preview_core),
    }


def _uuid(value: object, path: str, findings: list[dict[str, object]]) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        findings.append({"code": "invalid_uuid", "path": path})
        return None


def _scan_security(
    value: object,
    *,
    path: str,
    findings: list[dict[str, object]],
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            nested_path = f"{path}.{key}"
            if any(fragment in key_lower for fragment in FORBIDDEN_KEY_FRAGMENTS):
                findings.append({"code": "forbidden_field", "path": nested_path})
            if key_lower in UNAPPROVED_PII_KEYS and nested not in {None, ""}:
                findings.append({"code": "unapproved_pii", "path": nested_path})
            _scan_security(nested, path=nested_path, findings=findings)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _scan_security(nested, path=f"{path}[{index}]", findings=findings)
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in FORBIDDEN_VALUE_PATTERNS):
            findings.append({"code": "forbidden_value", "path": path})


def _validate_decimal_strings(
    value: object,
    *,
    path: str,
    findings: list[dict[str, object]],
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}.{key}"
            key_lower = str(key).lower()
            if (
                nested is not None
                and key_lower not in DECIMAL_EXEMPT_KEYS
                and any(fragment in key_lower for fragment in DECIMAL_FIELD_FRAGMENTS)
            ):
                if isinstance(nested, bool) or not isinstance(nested, str):
                    findings.append({"code": "decimal_must_be_string", "path": nested_path})
                else:
                    try:
                        Decimal(nested)
                    except InvalidOperation:
                        findings.append({"code": "invalid_decimal", "path": nested_path})
            _validate_decimal_strings(nested, path=nested_path, findings=findings)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_decimal_strings(nested, path=f"{path}[{index}]", findings=findings)


def validate_takeaway_import_package(
    *,
    manifest: dict[str, object],
    mapping: dict[str, object],
    records: list[dict[str, object]],
    expected_company_id: uuid.UUID | None = None,
    expected_brand_id: uuid.UUID | None = None,
) -> ImportValidationReport:
    findings: list[dict[str, object]] = []
    required_manifest = {
        "contract",
        "schema_version",
        "export_id",
        "generated_at",
        "cutoff_at",
        "timezone",
        "source",
        "scope",
        "mapping",
        "files",
        "omitted_sections",
        "record_totals",
        "security_attestation",
    }
    for key in sorted(required_manifest - set(manifest)):
        findings.append({"code": "manifest_required", "path": f"manifest.{key}"})
    if manifest.get("contract") != CONTRACT:
        findings.append({"code": "contract_mismatch", "path": "manifest.contract"})
    if manifest.get("schema_version") != SCHEMA_VERSION:
        findings.append({"code": "schema_version_mismatch", "path": "manifest.schema_version"})
    if manifest.get("timezone") != "Asia/Bangkok":
        findings.append({"code": "timezone_mismatch", "path": "manifest.timezone"})
    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("system") != "erp-pos-run" or source.get("read_only") is not True:
        findings.append({"code": "source_must_be_read_only_erp_pos_run", "path": "manifest.source"})
    attestation = manifest.get("security_attestation")
    if not isinstance(attestation, dict) or any(
        attestation.get(key) != 0
        for key in ("forbidden_field_findings", "unapproved_pii_findings", "unsafe_media_findings")
    ):
        findings.append({"code": "security_attestation_failed", "path": "manifest.security_attestation"})

    if mapping.get("contract") != MAPPING_CONTRACT:
        findings.append({"code": "mapping_contract_mismatch", "path": "mapping.contract"})
    if mapping.get("schema_version") != SCHEMA_VERSION:
        findings.append({"code": "mapping_schema_version_mismatch", "path": "mapping.schema_version"})
    if mapping.get("export_id") != manifest.get("export_id"):
        findings.append({"code": "mapping_export_mismatch", "path": "mapping.export_id"})
    company_mapping = mapping.get("company")
    brand_mapping = mapping.get("brand")
    if not isinstance(company_mapping, dict):
        findings.append({"code": "mapping_company_required", "path": "mapping.company"})
    elif expected_company_id is not None and company_mapping.get("target_id") != str(expected_company_id):
        findings.append({"code": "target_company_mismatch", "path": "mapping.company.target_id"})
    if not isinstance(brand_mapping, dict) or brand_mapping.get("business_type") != "takeaway":
        findings.append({"code": "takeaway_brand_mapping_required", "path": "mapping.brand"})
    elif expected_brand_id is not None and brand_mapping.get("target_id") != str(expected_brand_id):
        findings.append({"code": "target_brand_mismatch", "path": "mapping.brand.target_id"})

    export_id = _uuid(manifest.get("export_id"), "manifest.export_id", findings)
    _uuid(mapping.get("mapping_id"), "mapping.mapping_id", findings)
    if export_id is not None and mapping.get("export_id") != str(export_id):
        findings.append({"code": "mapping_export_id_invalid", "path": "mapping.export_id"})

    seen: set[tuple[str, str]] = set()
    section_counts: Counter[str] = Counter()
    source_ids_by_type: dict[str, set[str]] = {key: set() for key in RECORD_SECTION}
    record_error_indexes: set[int] = set()
    for index, record in enumerate(records):
        before = len(findings)
        path = f"records[{index}]"
        record_type = record.get("record_type")
        source_id = record.get("source_id")
        data = record.get("data")
        if record_type not in RECORD_SECTION:
            findings.append({"code": "unsupported_record_type", "path": f"{path}.record_type"})
        if _uuid(source_id, f"{path}.source_id", findings) is None:
            pass
        if not isinstance(data, dict):
            findings.append({"code": "record_data_required", "path": f"{path}.data"})
            data = {}
        if isinstance(record_type, str) and isinstance(source_id, str):
            identity = (record_type, source_id)
            if identity in seen:
                findings.append({"code": "duplicate_source_record", "path": path})
            seen.add(identity)
            if record_type in source_ids_by_type:
                source_ids_by_type[record_type].add(source_id)
                section_counts[RECORD_SECTION[record_type]] += 1
            expected_hash = canonical_record_hash(record_type, source_id, data)
            if record.get("source_hash") != expected_hash:
                findings.append({"code": "record_hash_mismatch", "path": f"{path}.source_hash"})
        updated_at = record.get("source_updated_at")
        if updated_at is not None and (not isinstance(updated_at, str) or not updated_at.endswith("Z")):
            findings.append({"code": "timestamp_must_be_utc", "path": f"{path}.source_updated_at"})
        _scan_security(data, path=f"{path}.data", findings=findings)
        _validate_decimal_strings(data, path=f"{path}.data", findings=findings)
        if len(findings) > before:
            record_error_indexes.add(index)

    category_ids = source_ids_by_type["category"]
    item_ids = source_ids_by_type["item"]
    location_ids = source_ids_by_type["stock_location"]
    branch_ids = {
        str(row.get("source_id"))
        for row in mapping.get("branches", [])
        if isinstance(row, dict)
    }
    for index, record in enumerate(records):
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        record_type = record.get("record_type")
        references: list[tuple[str, object, set[str]]] = []
        if record_type == "category":
            references.append(("parent_source_id", data.get("parent_source_id"), category_ids))
        elif record_type == "item":
            references.append(("category_source_id", data.get("category_source_id"), category_ids))
        elif record_type == "recipe":
            references.append(("output_item_source_id", data.get("output_item_source_id"), item_ids))
            references.append(("branch_source_id", data.get("branch_source_id"), branch_ids))
            for ingredient in data.get("ingredients", []):
                if isinstance(ingredient, dict):
                    references.append(("ingredients.item_source_id", ingredient.get("item_source_id"), item_ids))
        elif record_type in {"opening_stock", "opening_credit", "replenishment_policy", "stock_location"}:
            references.append(("branch_source_id", data.get("branch_source_id"), branch_ids))
        elif record_type in HISTORICAL_TYPES:
            references.append(("branch_source_id", data.get("branch_source_id"), branch_ids))
        if record_type in {"opening_stock", "replenishment_policy"}:
            references.extend(
                [
                    ("item_source_id", data.get("item_source_id"), item_ids),
                ]
            )
            if record_type == "opening_stock":
                references.append(("location_source_id", data.get("location_source_id"), location_ids))
        for field, reference, candidates in references:
            if reference is not None and str(reference) not in candidates:
                findings.append(
                    {
                        "code": "unresolved_reference",
                        "path": f"records[{index}].data.{field}",
                        "reference": str(reference),
                    }
                )
                record_error_indexes.add(index)

    declared_totals = manifest.get("record_totals")
    if isinstance(declared_totals, dict):
        known_sections = set(RECORD_SECTION.values())
        for section, count in declared_totals.items():
            if section in known_sections and section_counts.get(section, 0) != count:
                findings.append(
                    {
                        "code": "record_total_mismatch",
                        "path": f"manifest.record_totals.{section}",
                        "declared": count,
                        "actual": section_counts.get(section, 0),
                    }
                )
    historical_records = sum(
        section_counts[RECORD_SECTION[record_type]] for record_type in HISTORICAL_TYPES
    )
    rejected = len(record_error_indexes)
    return ImportValidationReport(
        status="ok" if not findings else "rejected",
        manifest_digest=digest_json(manifest),
        mapping_digest=digest_json(mapping),
        total_records=len(records),
        accepted_records=len(records) - rejected,
        rejected_records=rejected,
        section_counts=dict(sorted(section_counts.items())),
        historical_records=historical_records,
        side_effects_planned_for_history=0,
        findings=tuple(findings),
    )


class TakeawayImportService:
    def __init__(self, db: AsyncSession, current: TokenData):
        self.db = db
        self.current = current

    async def apply_synthetic(
        self,
        *,
        manifest: dict[str, object],
        mapping: dict[str, object],
        records: list[dict[str, object]],
    ) -> tuple[TakeawayImportBatch, bool]:
        return await self._apply_package(
            manifest=manifest,
            mapping=mapping,
            records=records,
            mode="synthetic_apply",
            allowed_source_environments={"synthetic"},
        )

    async def _apply_package(
        self,
        *,
        manifest: dict[str, object],
        mapping: dict[str, object],
        records: list[dict[str, object]],
        mode: str,
        allowed_source_environments: set[str],
    ) -> tuple[TakeawayImportBatch, bool]:
        brand_mapping = mapping.get("brand") if isinstance(mapping.get("brand"), dict) else {}
        target_brand_raw = brand_mapping.get("target_id")
        target_brand = uuid.UUID(str(target_brand_raw)) if target_brand_raw else None
        report = validate_takeaway_import_package(
            manifest=manifest,
            mapping=mapping,
            records=records,
            expected_company_id=self.current.company_id,
            expected_brand_id=self.current.brand_id,
        )
        if report.status != "ok":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=report.as_dict())
        source = manifest.get("source")
        if not isinstance(source, dict) or source.get("environment") not in allowed_source_environments:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Takeaway import source environment is not allowed for this operation",
            )
        if target_brand is None:
            raise HTTPException(status_code=422, detail="Target Takeaway Brand is required")
        brand_reference = await self.db.scalar(
            select(TakeawayReferenceProjection).where(
                TakeawayReferenceProjection.aggregate_type == "brand",
                TakeawayReferenceProjection.aggregate_id == target_brand,
                TakeawayReferenceProjection.company_id == self.current.company_id,
            )
        )
        if brand_reference is None or brand_reference.payload.get("business_type") != "takeaway":
            raise HTTPException(status_code=409, detail="Mapped Takeaway Brand is not projected")
        existing = await self.db.scalar(
            select(TakeawayImportBatch).where(
                TakeawayImportBatch.manifest_digest == report.manifest_digest
            )
        )
        if existing is not None:
            return existing, True
        batch = TakeawayImportBatch(
            source_system="erp-pos-run",
            source_snapshot=str(source.get("snapshot_id")),
            manifest_digest=report.manifest_digest,
            mode=mode,
            status="applying",
            total_records=report.total_records,
            accepted_records=report.accepted_records,
            rejected_records=0,
            report=report.as_dict(),
        )
        self.db.add(batch)
        await self.db.flush()
        branch_map = {
            str(row["source_id"]): uuid.UUID(str(row["target_id"]))
            for row in mapping.get("branches", [])
            if isinstance(row, dict) and row.get("source_id") and row.get("target_id")
        }
        location_override_map = {
            str(row["source_id"]): uuid.UUID(str(row["target_id"]))
            for row in mapping.get("locations", [])
            if isinstance(row, dict) and row.get("source_id") and row.get("target_id")
        }
        records_by_type: dict[str, list[dict[str, object]]] = {
            record_type: [] for record_type in RECORD_SECTION
        }
        for record in records:
            records_by_type[str(record["record_type"])].append(record)

        target_records: dict[tuple[str, str], tuple[str, uuid.UUID | None, str]] = {}
        category_map: dict[str, uuid.UUID] = {}
        item_map: dict[str, uuid.UUID] = {}
        location_map: dict[str, uuid.UUID] = {}

        for record in records_by_type["unit"]:
            source_id = str(record["source_id"])
            data = record["data"]
            assert isinstance(data, dict)
            target = TakeawayUnit(
                company_id=self.current.company_id,
                code=str(data["code"]),
                name=str(data["name"]),
                name_en=data.get("name_en"),
                decimal_places=int(data.get("decimal_places", 0)),
                is_active=bool(data.get("is_active", True)),
            )
            self.db.add(target)
            await self.db.flush()
            target_records[("unit", source_id)] = ("takeaway_unit", target.id, "imported")

        for record in records_by_type["category"]:
            source_id = str(record["source_id"])
            data = record["data"]
            assert isinstance(data, dict)
            target = TakeawayCategory(
                company_id=self.current.company_id,
                brand_id=target_brand,
                code=str(data.get("code") or f"legacy-{source_id[:8]}").lower(),
                name=str(data["name"]),
                sort_order=int(data.get("sort_order", 0)),
                is_active=bool(data.get("is_active", True)),
            )
            self.db.add(target)
            await self.db.flush()
            category_map[source_id] = target.id
            target_records[("category", source_id)] = (
                "takeaway_category",
                target.id,
                "imported",
            )

        for record in records_by_type["item"]:
            source_id = str(record["source_id"])
            data = record["data"]
            assert isinstance(data, dict)
            target = TakeawayCatalogItem(
                company_id=self.current.company_id,
                brand_id=target_brand,
                category_id=category_map.get(str(data.get("category_source_id"))),
                sku=str(data["sku"]),
                barcode=data.get("barcode"),
                name=str(data["name"]),
                unit=str(data["unit_code"]),
                price=Decimal(str(data["selling_price"])),
                tax_rate=Decimal(str(data["vat_rate"])),
                track_stock=data.get("inventory_role") != "not_stocked",
                is_active=bool(data.get("is_active", True)),
                source_metadata={
                    "import_batch_id": str(batch.id),
                    "source_id": source_id,
                    "inventory_role": data.get("inventory_role"),
                    "brand_scope": data.get("brand_scope"),
                    "cost_price": data.get("cost_price"),
                    "product_type": data.get("product_type"),
                    "is_for_sale": data.get("is_for_sale"),
                    "is_for_purchase": data.get("is_for_purchase"),
                },
            )
            self.db.add(target)
            await self.db.flush()
            item_map[source_id] = target.id
            target_records[("item", source_id)] = (
                "takeaway_catalog_item",
                target.id,
                "imported",
            )

        for record in records_by_type["stock_location"]:
            source_id = str(record["source_id"])
            data = record["data"]
            assert isinstance(data, dict)
            target = TakeawayStockLocation(
                id=location_override_map.get(source_id, uuid.uuid4()),
                company_id=self.current.company_id,
                branch_id=branch_map[str(data["branch_source_id"])],
                code=str(data["code"]),
                name=str(data["name"]),
                location_type=str(data["location_type"]),
                is_active=bool(data.get("is_active", True)),
            )
            self.db.add(target)
            await self.db.flush()
            location_map[source_id] = target.id
            target_records[("stock_location", source_id)] = (
                "takeaway_stock_location",
                target.id,
                "imported",
            )

        for record in records_by_type["recipe"]:
            source_id = str(record["source_id"])
            data = record["data"]
            assert isinstance(data, dict)
            target = TakeawayRecipe(
                company_id=self.current.company_id,
                brand_id=target_brand,
                branch_id=branch_map.get(str(data.get("branch_source_id"))),
                output_item_id=item_map[str(data["output_item_source_id"])],
                recipe_type=str(data["recipe_type"]),
                version_no=int(data["version_no"]),
                effective_from=_date(data.get("effective_from")),
                effective_to=_date(data.get("effective_to")),
                name=str(data["name"]),
                yield_qty=Decimal(str(data["yield_qty"])),
                yield_unit=str(data["yield_unit_code"]),
                loss_percent=Decimal(str(data["loss_percent"])),
                is_active=bool(data.get("is_active", True)),
            )
            self.db.add(target)
            await self.db.flush()
            for ingredient in data.get("ingredients", []):
                assert isinstance(ingredient, dict)
                self.db.add(
                    TakeawayRecipeIngredient(
                        recipe_id=target.id,
                        item_id=item_map[str(ingredient["item_source_id"])],
                        sku=str(ingredient["sku"]),
                        quantity=Decimal(str(ingredient["quantity"])),
                        unit=str(ingredient["unit_code"]),
                        sort_order=int(ingredient.get("sort_order", 0)),
                    )
                )
            target_records[("recipe", source_id)] = (
                "takeaway_recipe",
                target.id,
                "imported",
            )

        for record in records_by_type["replenishment_policy"]:
            source_id = str(record["source_id"])
            data = record["data"]
            assert isinstance(data, dict)
            target = TakeawayReplenishmentPolicy(
                company_id=self.current.company_id,
                brand_id=target_brand,
                branch_id=branch_map[str(data["branch_source_id"])],
                item_id=item_map[str(data["item_source_id"])],
                is_enabled=bool(data.get("is_enabled", True)),
                safety_stock_percent=Decimal(str(data["safety_stock_percent"])),
                safety_stock_qty=Decimal(str(data["safety_stock_qty"])),
                pack_size=Decimal(str(data["pack_size"])),
                lead_time_days=int(data["lead_time_days"]),
                forecast_method=str(data["forecast_method"]),
                minimum_order_qty=Decimal(str(data["minimum_order_qty"])),
            )
            self.db.add(target)
            await self.db.flush()
            target_records[("replenishment_policy", source_id)] = (
                "takeaway_replenishment_policy",
                target.id,
                "imported",
            )

        stock_service = TakeawayService(self.db, self.current)
        for record in records_by_type["opening_stock"]:
            source_id = str(record["source_id"])
            data = record["data"]
            assert isinstance(data, dict)
            quantity = Decimal(str(data["qty_on_hand"]))
            if quantity > 0:
                balance = await stock_service._apply_stock(
                    location_id=location_map[str(data["location_source_id"])],
                    item_id=item_map[str(data["item_source_id"])],
                    lot_code=str(data.get("lot_code") or ""),
                    quantity_delta=quantity,
                    unit_cost=Decimal(str(data["cost_per_unit"])),
                    movement_type="opening_import",
                    idempotency_key=f"takeaway-import:{batch.id}:stock:{source_id}",
                    brand_id=target_brand,
                    branch_id=branch_map[str(data["branch_source_id"])],
                )
                balance.reserved_qty = Decimal(str(data["qty_reserved"]))
                target_id = balance.id
            else:
                target_id = None
            target_records[("opening_stock", source_id)] = (
                "takeaway_stock_balance",
                target_id,
                "imported",
            )

        for record in records_by_type["opening_credit"]:
            source_id = str(record["source_id"])
            data = record["data"]
            assert isinstance(data, dict)
            target = TakeawayCreditAccount(
                company_id=self.current.company_id,
                brand_id=target_brand,
                branch_id=branch_map[str(data["branch_source_id"])],
                credit_limit=Decimal(str(data["credit_limit"])),
                balance=Decimal(str(data["balance"])),
                status="active",
            )
            self.db.add(target)
            await self.db.flush()
            if Decimal(str(data["balance"])) > 0:
                self.db.add(
                    TakeawayCreditEntry(
                        account_id=target.id,
                        entry_type="adjustment",
                        amount=Decimal(str(data["balance"])),
                        reference_type="opening_import",
                        reference_id=batch.id,
                        idempotency_key=f"takeaway-import:{batch.id}:credit:{source_id}",
                    )
                )
            target_records[("opening_credit", source_id)] = (
                "takeaway_credit_account",
                target.id,
                "imported",
            )

        for record_type in sorted(HISTORICAL_TYPES):
            for record in records_by_type[record_type]:
                source_id = str(record["source_id"])
                data = record["data"]
                assert isinstance(data, dict)
                branch_source_id = data.get("branch_source_id")
                target = TakeawayHistoricalArchive(
                    company_id=self.current.company_id,
                    brand_id=target_brand,
                    branch_id=branch_map.get(str(branch_source_id)),
                    import_batch_id=batch.id,
                    record_type=record_type,
                    source_id=source_id,
                    business_date=_business_date(data),
                    document_number=_document_number(data),
                    source_hash=str(record["source_hash"]),
                    snapshot=data,
                )
                self.db.add(target)
                await self.db.flush()
                target_records[(record_type, source_id)] = (
                    "takeaway_historical_archive",
                    target.id,
                    "archived",
                )

        for record in records:
            record_type = str(record["record_type"])
            source_id = str(record["source_id"])
            target_type, target_id, record_status = target_records.get(
                (record_type, source_id),
                ("validated", None, "validated"),
            )
            self.db.add(
                TakeawayImportRecord(
                    batch_id=batch.id,
                    source_type=record_type,
                    source_id=source_id,
                    target_type=target_type,
                    target_id=target_id,
                    source_digest=str(record["source_hash"]),
                    status=record_status,
                )
            )
        batch.status = "completed"
        await self.db.commit()
        await self.db.refresh(batch)
        return batch, False

    async def execute_approved_cutover(
        self,
        *,
        manifest: dict[str, object],
        mapping: dict[str, object],
        records: list[dict[str, object]],
        trusted_public_keys: dict[str, str],
        preview_digest: str,
        execution_key: str,
        approval_reference: str,
        backup_reference: str,
        rollback_reference: str,
    ) -> tuple[TakeawayCutoverRun, bool]:
        existing = await self.db.scalar(
            select(TakeawayCutoverRun).where(
                TakeawayCutoverRun.company_id == self.current.company_id,
                TakeawayCutoverRun.execution_key == execution_key,
            )
        )
        if existing is not None:
            return existing, True
        preview = build_takeaway_cutover_preview(
            manifest=manifest,
            mapping=mapping,
            records=records,
            expected_company_id=self.current.company_id,
            expected_brand_id=self.current.brand_id,
            trusted_public_keys=trusted_public_keys,
        )
        if not preview["ready"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Takeaway cutover preview has blockers", "preview": preview},
            )
        if preview["preview_digest"] != preview_digest:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cutover preview changed; run preview and approve again",
            )
        batch, replayed = await self._apply_package(
            manifest=manifest,
            mapping=mapping,
            records=records,
            mode="approved_cutover",
            allowed_source_environments={"approved_snapshot"},
        )
        brand_mapping = mapping.get("brand")
        source = manifest.get("source")
        if not isinstance(brand_mapping, dict) or not isinstance(source, dict):
            raise HTTPException(status_code=422, detail="Approved cutover scope is incomplete")
        brand_id = uuid.UUID(str(brand_mapping["target_id"]))
        imported_count = len(records)
        reconciliation = {
            "status": "matched" if batch.accepted_records == imported_count and batch.rejected_records == 0 else "mismatch",
            "source_record_count": imported_count,
            "target_import_record_count": batch.accepted_records,
            "rejected_record_count": batch.rejected_records,
            "control_totals": takeaway_import_control_totals(records),
            "historical_side_effects": 0,
            "batch_replayed": replayed,
        }
        run = TakeawayCutoverRun(
            company_id=self.current.company_id,
            brand_id=brand_id,
            batch_id=batch.id,
            execution_key=execution_key,
            export_id=uuid.UUID(str(manifest["export_id"])),
            source_snapshot=str(source["snapshot_id"]),
            manifest_digest=str(preview["manifest_digest"]),
            mapping_digest=str(preview["mapping_digest"]),
            preview_digest=preview_digest,
            status="completed",
            approved_by=self.current.user_id,
            approval_reference=approval_reference,
            backup_reference=backup_reference,
            rollback_reference=rollback_reference,
            report=preview,
            reconciliation=reconciliation,
            executed_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run, False

    async def list_cutover_runs(self) -> list[TakeawayCutoverRun]:
        query = select(TakeawayCutoverRun).where(
            TakeawayCutoverRun.company_id == self.current.company_id,
        )
        if self.current.brand_id is not None:
            query = query.where(TakeawayCutoverRun.brand_id == self.current.brand_id)
        return list(
            (
                await self.db.scalars(
                    query.order_by(TakeawayCutoverRun.created_at.desc()).limit(100)
                )
            ).all()
        )


def _date(value: object) -> date | None:
    if value in {None, ""}:
        return None
    return date.fromisoformat(str(value)[:10])


def _business_date(data: dict[str, object]) -> date | None:
    for key in ("business_date", "business_at", "opened_at", "planned_at", "occurred_at"):
        if data.get(key):
            return _date(data[key])
    return None


def _document_number(data: dict[str, object]) -> str | None:
    for key in (
        "legacy_document_number",
        "order_number",
        "shift_number",
        "batch_number",
        "transfer_number",
    ):
        if data.get(key):
            return str(data[key])
    return None
