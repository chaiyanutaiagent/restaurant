from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import DeviceTokenData, TokenData
from app.models.audit import AuditLog
from app.models.offline_sync import OfflinePosOperation, OfflinePosOperationEvent
from app.schemas.restaurant import WapOfflinePaidOrderRequest


OFFLINE_SCHEMA_VERSION = "offline-pos-v1"
OFFLINE_ACTIVE_STATES = {
    "pending_sync",
    "syncing",
    "server_acknowledged",
    "unknown",
    "needs_review",
    "rejected",
    "quarantined",
}


class OfflineSyncError(ValueError):
    def __init__(self, code: str, message: str, *, state: str = "rejected") -> None:
        super().__init__(message)
        self.code = code
        self.state = state


def _allowlist(raw: str) -> set[str]:
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def offline_scope_enabled(company_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
    return (
        settings.pos_offline_mode_enabled
        and str(company_id).lower() in _allowlist(settings.pos_offline_company_allowlist)
        and str(branch_id).lower() in _allowlist(settings.pos_offline_branch_allowlist)
    )


def _decimal_text(value: Decimal | int | float | str | None, places: int) -> str | None:
    if value is None:
        return None
    quantum = Decimal("1").scaleb(-places)
    return format(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP), f".{places}f")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    # JavaScript Date#toISOString uses millisecond precision. Pinning the
    # canonical document to the same representation keeps browser/server
    # request hashes byte-for-byte identical.
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def offline_request_document(payload: WapOfflinePaidOrderRequest) -> dict:
    """Stable, secret-free request document shared with the encrypted client outbox."""
    return {
        "schema_version": payload.schema_version,
        "client_operation_id": payload.client_operation_id,
        "idempotency_key": payload.idempotency_key,
        "company_id": str(payload.company_id) if payload.company_id else None,
        "brand_id": str(payload.brand_id) if payload.brand_id else None,
        "branch_id": str(payload.branch_id) if payload.branch_id else None,
        "station_key": payload.station_key,
        "shift_id": str(payload.shift_id) if payload.shift_id else None,
        "operation_type": payload.operation_type,
        "sequence_no": payload.sequence_no,
        "created_at_device": _iso(payload.local_created_at),
        "price_snapshot_version": payload.price_snapshot_version,
        "currency": payload.currency,
        "authorization_digest": hashlib.sha256(
            (payload.offline_authorization or "").encode("utf-8")
        ).hexdigest(),
        "payload": {
            "items": [
                {
                    "product_id": str(item.product_id),
                    "qty": item.qty,
                    "special_request": item.special_request,
                    "expected_unit_price": _decimal_text(item.expected_unit_price, 4),
                    "expected_price_version": item.expected_price_version,
                }
                for item in payload.items
            ],
            "payment_method": payload.payment_method,
            "paid_amount": _decimal_text(payload.paid_amount, 2),
            "payments": [
                {
                    "payment_method": payment.payment_method,
                    "amount": _decimal_text(payment.amount, 2),
                    "reference_no": payment.reference_no,
                }
                for payment in payload.payments
            ],
            "customer_name": payload.customer_name,
            "customer_phone": payload.customer_phone,
            "customer_tax_id": payload.customer_tax_id,
            "note": payload.note,
            "location_id": str(payload.location_id) if payload.location_id else None,
        },
    }


def offline_request_hash(payload: WapOfflinePaidOrderRequest) -> str:
    encoded = json.dumps(
        offline_request_document(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class OfflineSyncService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def assert_runtime_scope(
        current: TokenData,
        device: DeviceTokenData | None,
        payload: WapOfflinePaidOrderRequest,
        *,
        brand_id: uuid.UUID | None,
    ) -> None:
        if not settings.pos_offline_mode_enabled:
            raise OfflineSyncError(
                "offline_processing_disabled",
                "Offline processing is disabled; inquiry and export remain available",
            )
        if current.branch_id is None or not offline_scope_enabled(current.company_id, current.branch_id):
            raise OfflineSyncError("offline_scope_denied", "Company or Branch is not allowed for Offline UAT")
        if device is None:
            raise OfflineSyncError("paired_counter_required", "A paired Counter device is required")
        if (
            device.company_id != current.company_id
            or device.branch_id != current.branch_id
            or device.device_type != "counter"
            or device.station_key is not None
            or (brand_id is not None and device.brand_id != brand_id)
        ):
            raise OfflineSyncError("device_scope_mismatch", "Counter device scope does not match staff context")
        required = {
            "schema_version": payload.schema_version,
            "client_operation_id": payload.client_operation_id,
            "idempotency_key": payload.idempotency_key,
            "request_hash": payload.request_hash,
            "company_id": payload.company_id,
            "branch_id": payload.branch_id,
            "station_key": payload.station_key,
            "operation_type": payload.operation_type,
            "sequence_no": payload.sequence_no,
            "price_snapshot_version": payload.price_snapshot_version,
            "shift_id": payload.shift_id,
            "location_id": payload.location_id,
            "local_created_at": payload.local_created_at,
            "offline_authorization": payload.offline_authorization,
        }
        missing = [key for key, value in required.items() if value is None]
        if missing:
            raise OfflineSyncError("invalid_envelope", f"Offline envelope is missing: {', '.join(missing)}")
        if payload.schema_version != OFFLINE_SCHEMA_VERSION:
            raise OfflineSyncError("unsupported_schema", "Offline schema version is not supported", state="quarantined")
        if payload.operation_type != "cash_sale":
            raise OfflineSyncError("operation_not_allowed", "Only offline cash sale is enabled in this UAT")
        if payload.payment_method != "cash" or any(item.payment_method != "cash" for item in payload.payments):
            raise OfflineSyncError("payment_not_allowed_offline", "Only THB cash is allowed offline")
        if payload.currency != "THB":
            raise OfflineSyncError("currency_not_allowed_offline", "Only THB is allowed offline")
        if payload.client_operation_id != payload.client_order_id:
            raise OfflineSyncError("operation_identity_mismatch", "Client operation id must match client order id", state="quarantined")
        expected_key = f"offline-sale:{device.device_id}:{payload.client_operation_id}"
        if payload.idempotency_key != expected_key:
            raise OfflineSyncError("idempotency_mismatch", "Offline idempotency key is invalid", state="quarantined")
        if payload.company_id != current.company_id or payload.branch_id != current.branch_id:
            raise OfflineSyncError("tenant_scope_mismatch", "Offline request Company or Branch does not match", state="quarantined")
        if payload.brand_id != brand_id:
            raise OfflineSyncError("brand_scope_mismatch", "Offline request Brand does not match", state="quarantined")
        if payload.station_key != device.device_code:
            raise OfflineSyncError("station_scope_mismatch", "Offline request Station does not match paired Counter", state="quarantined")

    async def prepare(
        self,
        current: TokenData,
        device: DeviceTokenData | None,
        payload: WapOfflinePaidOrderRequest,
        *,
        brand_id: uuid.UUID | None,
    ) -> tuple[OfflinePosOperation, bool]:
        self.assert_runtime_scope(current, device, payload, brand_id=brand_id)
        assert current.branch_id is not None
        assert device is not None
        assert payload.client_operation_id is not None
        assert payload.idempotency_key is not None
        assert payload.request_hash is not None
        assert payload.sequence_no is not None
        assert payload.shift_id is not None
        assert payload.station_key is not None
        assert payload.price_snapshot_version is not None
        assert payload.local_created_at is not None
        server_hash = offline_request_hash(payload)

        existing = await self.db.scalar(
            select(OfflinePosOperation)
            .where(
                OfflinePosOperation.company_id == current.company_id,
                OfflinePosOperation.branch_id == current.branch_id,
                or_(
                    OfflinePosOperation.client_operation_id == payload.client_operation_id,
                    OfflinePosOperation.idempotency_key == payload.idempotency_key,
                ),
            )
            .with_for_update()
        )
        if existing is not None:
            if (
                existing.client_operation_id != payload.client_operation_id
                or existing.idempotency_key != payload.idempotency_key
                or existing.request_hash != payload.request_hash
                or existing.server_request_hash != server_hash
            ):
                # Never let a conflicting replay rewrite the canonical outcome.
                # The attempt is quarantined in the append-only event/audit trail,
                # while the first accepted operation remains authoritative.
                await self._event(
                    existing,
                    event_key=f"payload-mismatch:{payload.request_hash}",
                    event_type="payload_mismatch",
                    to_state=existing.status,
                    actor_user_id=current.user_id,
                    evidence={
                        "attempt_state": "quarantined",
                        "received_client_operation_id": payload.client_operation_id,
                        "received_idempotency_key": payload.idempotency_key,
                        "received_hash": payload.request_hash,
                        "server_hash": server_hash,
                    },
                )
                await self.db.commit()
                raise OfflineSyncError(
                    "duplicate_request",
                    "Client operation was replayed with a different payload",
                    state="quarantined",
                )
            existing.retry_count += 1
            await self._event(
                existing,
                event_key=f"replay:{existing.retry_count}",
                event_type="replay",
                to_state=existing.status,
                actor_user_id=current.user_id,
                evidence={"retry_count": existing.retry_count},
            )
            await self.db.commit()
            return existing, True

        sequence_collision = await self.db.scalar(
            select(OfflinePosOperation.id).where(
                OfflinePosOperation.company_id == current.company_id,
                OfflinePosOperation.branch_id == current.branch_id,
                OfflinePosOperation.device_id == device.device_id,
                OfflinePosOperation.shift_id == payload.shift_id,
                OfflinePosOperation.sequence_no == payload.sequence_no,
            )
        )
        if sequence_collision is not None:
            raise OfflineSyncError(
                "sequence_collision",
                "Offline sequence number already belongs to another operation",
                state="quarantined",
            )

        operation = OfflinePosOperation(
            company_id=current.company_id,
            brand_id=brand_id,
            branch_id=current.branch_id,
            device_id=device.device_id,
            shift_id=payload.shift_id,
            user_id=current.user_id,
            schema_version=payload.schema_version,
            operation_type=payload.operation_type,
            client_operation_id=payload.client_operation_id,
            idempotency_key=payload.idempotency_key,
            request_hash=payload.request_hash,
            server_request_hash=server_hash,
            sequence_no=payload.sequence_no,
            station_key=payload.station_key,
            price_snapshot_version=payload.price_snapshot_version,
            created_at_device=payload.local_created_at,
            status="quarantined" if payload.request_hash != server_hash else "pending_sync",
            error_code="request_hash_mismatch" if payload.request_hash != server_hash else None,
            error_message="Offline request hash does not match canonical payload" if payload.request_hash != server_hash else None,
            retain_until=datetime.now(timezone.utc) + timedelta(days=settings.pos_offline_retention_days),
        )
        self.db.add(operation)
        await self.db.flush()
        await self._event(
            operation,
            event_key="received",
            event_type="received",
            to_state=operation.status,
            actor_user_id=current.user_id,
            evidence={
                "schema_version": operation.schema_version,
                "sequence_no": operation.sequence_no,
                "request_hash_valid": payload.request_hash == server_hash,
            },
        )
        await self.db.commit()
        if operation.status == "quarantined":
            raise OfflineSyncError(
                "request_hash_mismatch",
                "Offline request hash does not match canonical payload",
                state="quarantined",
            )
        return operation, False

    async def transition(
        self,
        operation: OfflinePosOperation,
        state: str,
        *,
        actor_user_id: uuid.UUID | None,
        event_type: str,
        error_code: str | None = None,
        error_message: str | None = None,
        result_snapshot: dict | None = None,
        sale_order_id: uuid.UUID | None = None,
    ) -> OfflinePosOperation:
        previous = operation.status
        operation.status = state
        operation.error_code = error_code
        operation.error_message = error_message
        if result_snapshot is not None:
            operation.result_snapshot = result_snapshot
        if sale_order_id is not None:
            operation.sale_order_id = sale_order_id
        now = datetime.now(timezone.utc)
        if state in {"server_acknowledged", "reconciled"} and operation.acknowledged_at is None:
            operation.acknowledged_at = now
        if state == "reconciled":
            operation.reconciled_at = now
        await self._event(
            operation,
            event_key=f"{event_type}:{state}:{operation.retry_count}",
            event_type=event_type,
            to_state=state,
            actor_user_id=actor_user_id,
            from_state=previous,
            evidence={"error_code": error_code, "sale_order_id": str(sale_order_id) if sale_order_id else None},
        )
        await self.db.commit()
        await self.db.refresh(operation)
        return operation

    async def get_scoped(
        self,
        current: TokenData,
        client_operation_id: str,
    ) -> OfflinePosOperation | None:
        if current.branch_id is None:
            return None
        return await self.db.scalar(
            select(OfflinePosOperation).where(
                OfflinePosOperation.company_id == current.company_id,
                OfflinePosOperation.branch_id == current.branch_id,
                OfflinePosOperation.client_operation_id == client_operation_id,
            )
        )

    async def list_scoped(
        self,
        current: TokenData,
        *,
        limit: int = 250,
    ) -> list[OfflinePosOperation]:
        if current.branch_id is None:
            return []
        return list((await self.db.scalars(
            select(OfflinePosOperation)
            .where(
                OfflinePosOperation.company_id == current.company_id,
                OfflinePosOperation.branch_id == current.branch_id,
            )
            .order_by(OfflinePosOperation.created_at.desc())
            .limit(limit)
        )).all())

    async def purge_reconciled(self, current: TokenData) -> int:
        if current.branch_id is None:
            return 0
        now = datetime.now(timezone.utc)
        rows = list((await self.db.scalars(
            select(OfflinePosOperation).where(
                OfflinePosOperation.company_id == current.company_id,
                OfflinePosOperation.branch_id == current.branch_id,
                OfflinePosOperation.status == "reconciled",
                OfflinePosOperation.retain_until <= now,
            )
        )).all())
        for row in rows:
            previous = row.status
            row.status = "purged"
            row.purged_at = now
            row.result_snapshot = None
            await self._event(
                row,
                event_key="retention-purge",
                event_type="retention_purge",
                from_state=previous,
                to_state="purged",
                actor_user_id=current.user_id,
                evidence={"retain_until": row.retain_until.isoformat() if row.retain_until else None},
            )
        await self.db.commit()
        return len(rows)

    async def resolve_exception(
        self,
        current: TokenData,
        client_operation_id: str,
        *,
        reason: str,
    ) -> OfflinePosOperation:
        operation = await self.get_scoped(current, client_operation_id)
        if operation is None:
            raise OfflineSyncError("operation_not_found", "Offline operation not found")
        if operation.status not in {"unknown", "needs_review", "quarantined"}:
            raise OfflineSyncError(
                "operation_not_resolvable",
                "Only Unknown, Needs review, or Quarantined operations can be resolved",
            )
        return await self.transition(
            operation,
            "rejected",
            actor_user_id=current.user_id,
            event_type="manual_resolution",
            error_code="manually_rejected",
            error_message=reason,
        )

    async def record_rejected_request(
        self,
        current: TokenData,
        payload: WapOfflinePaidOrderRequest,
        error: OfflineSyncError,
    ) -> None:
        self.db.add(AuditLog(
            company_id=current.company_id,
            branch_id=current.branch_id,
            user_id=current.user_id,
            action="pos.offline.request_rejected",
            resource="OfflinePosOperation",
            resource_id=payload.client_operation_id or payload.client_order_id,
            new_value={
                "code": error.code,
                "state": error.state,
                "schema_version": payload.schema_version,
                "request_hash": payload.request_hash,
            },
        ))
        await self.db.commit()

    async def _event(
        self,
        operation: OfflinePosOperation,
        *,
        event_key: str,
        event_type: str,
        to_state: str,
        actor_user_id: uuid.UUID | None,
        evidence: dict,
        from_state: str | None = None,
    ) -> None:
        self.db.add(OfflinePosOperationEvent(
            operation_id=operation.id,
            company_id=operation.company_id,
            branch_id=operation.branch_id,
            actor_user_id=actor_user_id,
            event_key=event_key,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            evidence=evidence,
        ))


def serialize_offline_operation(operation: OfflinePosOperation) -> dict:
    return {
        "operation_id": str(operation.id),
        "client_operation_id": operation.client_operation_id,
        "idempotency_key": operation.idempotency_key,
        "schema_version": operation.schema_version,
        "operation_type": operation.operation_type,
        "sequence_no": operation.sequence_no,
        "station_key": operation.station_key,
        "shift_id": str(operation.shift_id),
        "device_id": str(operation.device_id),
        "sale_order_id": str(operation.sale_order_id) if operation.sale_order_id else None,
        "status": operation.status,
        "request_hash": operation.request_hash,
        "retry_count": operation.retry_count,
        "error_code": operation.error_code,
        "error": operation.error_message,
        "acknowledged_at": operation.acknowledged_at.isoformat() if operation.acknowledged_at else None,
        "reconciled_at": operation.reconciled_at.isoformat() if operation.reconciled_at else None,
        "retain_until": operation.retain_until.isoformat() if operation.retain_until else None,
        "purged_at": operation.purged_at.isoformat() if operation.purged_at else None,
        "result": operation.result_snapshot,
        "created_at": operation.created_at.isoformat() if operation.created_at else None,
        "updated_at": operation.updated_at.isoformat() if operation.updated_at else None,
    }
