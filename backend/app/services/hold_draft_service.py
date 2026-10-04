from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pos import CashierShift, PosHoldDraft, PosHoldDraftAudit
from app.models.restaurant import DiningTable
from app.models.settings import BranchSettings
from app.models.stock import StockBalance
from app.models.user import User, UserBranch
from app.schemas.pos import (
    HoldDraftActionRequest,
    HoldDraftClaimRead,
    HoldDraftCreateRequest,
    HoldDraftItemRequest,
    HoldDraftRead,
    HoldDraftUpdateRequest,
)
from app.schemas.pricing import PricingCalculateRequest, PricingLineRequest
from app.services.pricing_service import PricingResult, PricingService, canonical_hash


DEFAULT_DRAFT_TTL_MINUTES = 120
DEFAULT_CLAIM_TTL_SECONDS = 120
ACTIVE_STATUSES = {"active", "claimed"}


def hold_error(http_status: int, code: str, message: str, **context: Any) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message, **context},
    )


class HoldDraftService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _read(draft: PosHoldDraft) -> HoldDraftRead:
        return HoldDraftRead(
            id=draft.id,
            draft_no=draft.draft_no,
            company_id=draft.company_id,
            brand_id=draft.brand_id,
            branch_id=draft.branch_id,
            location_id=draft.location_id,
            origin_shift_id=draft.origin_shift_id,
            owner_user_id=draft.owner_user_id,
            assignee_user_id=draft.assignee_user_id,
            origin_device_id=draft.origin_device_id,
            origin_device_code=draft.origin_device_code,
            parent_draft_id=draft.parent_draft_id,
            converted_order_id=draft.converted_order_id,
            label=draft.label,
            source_type=draft.source_type,
            table_id=draft.table_id,
            queue_label=draft.queue_label,
            customer_id=draft.customer_id,
            customer_display=draft.customer_display,
            note=draft.note,
            content=draft.content_json,
            pricing_context=draft.pricing_context,
            pricing_snapshot=draft.pricing_snapshot,
            last_revalidation=draft.last_revalidation,
            status=draft.status,
            version=draft.version,
            claim_id=draft.claim_id,
            claimed_by=draft.claimed_by,
            claimed_device_id=draft.claimed_device_id,
            claim_expires_at=draft.claim_expires_at,
            expires_at=draft.expires_at,
            resumed_at=draft.resumed_at,
            resumed_by=draft.resumed_by,
            expired_at=draft.expired_at,
            cancelled_at=draft.cancelled_at,
            cancel_reason=draft.cancel_reason,
            converted_at=draft.converted_at,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )

    @staticmethod
    def _channel(source_type: str) -> str:
        if source_type == "takeaway":
            return "takeaway"
        if source_type == "restaurant_table":
            return "restaurant_table"
        if source_type == "restaurant_quick_service":
            return "restaurant_quick_service"
        return "pos"

    @staticmethod
    def _pricing_items(items: list[HoldDraftItemRequest]) -> list[PricingLineRequest]:
        return [
            PricingLineRequest(
                product_id=item.product_id,
                variant_id=item.variant_id,
                qty=item.qty,
                discount_amount=item.discount_amount,
                discount_type=item.discount_type,
                price_override=item.price_override,
            )
            for item in items
        ]

    @staticmethod
    def _stored_pricing_items(content: dict[str, Any]) -> list[HoldDraftItemRequest]:
        return [HoldDraftItemRequest.model_validate(item) for item in content.get("pricing_items", [])]

    async def _calculate(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        source_type: str,
        items: list[HoldDraftItemRequest],
        order_discount: Decimal,
        loyalty_discount: Decimal,
        customer_id: uuid.UUID | None,
        currency: str,
        cart_version: int,
        operation_key: str,
        lock_prices: bool = False,
    ) -> PricingResult:
        return await PricingService(self.db).calculate(
            company_id=company_id,
            branch_id=branch_id,
            brand_id=brand_id,
            payload=PricingCalculateRequest(
                items=self._pricing_items(items),
                discount_amount=Decimal(order_discount) + Decimal(loyalty_discount),
                discount_type="amount",
                channel=self._channel(source_type),
                currency=currency,
                customer_id=customer_id,
                idempotency_key=operation_key,
                cart_version=cart_version,
            ),
            lock_prices=lock_prices,
        )

    @staticmethod
    def _cart_snapshot(result: PricingResult) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for line in result.lines:
            qty = Decimal(line.request.qty)
            effective_unit = (
                line.applied_unit_price - (line.line_discount_amount / qty)
                if qty > 0
                else line.applied_unit_price
            )
            items.append(
                {
                    "product_id": str(line.product.id),
                    "variant_id": str(line.variant.id) if line.variant else None,
                    "product_name": line.product.name,
                    "variant_name": line.variant.name if line.variant else None,
                    "sku": line.variant.sku if line.variant else line.product.sku,
                    "unit_code": line.product.unit.code if line.product.unit else None,
                    "qty": str(qty),
                    "unit_price": str(effective_unit),
                    "original_price": str(line.applied_unit_price),
                    "discount_amount": str(line.request.discount_amount),
                    "discount_type": line.request.discount_type,
                    "vat_type": line.vat_type,
                    "vat_rate": str(line.vat_rate),
                    "subtotal": str(line.line_subtotal),
                    "vat_amount": str(line.vat_amount),
                    "expected_price_version": line.price_version,
                    "price_override": (
                        line.request.price_override.model_dump(mode="json")
                        if line.request.price_override is not None
                        else None
                    ),
                }
            )
        return {
            "items": items,
            "pricing": result.snapshot(),
        }

    @staticmethod
    def _price_changes(draft: PosHoldDraft, result: PricingResult) -> list[dict[str, Any]]:
        previous = (draft.pricing_snapshot or {}).get("lines", [])
        current = result.snapshot().get("lines", [])
        changes: list[dict[str, Any]] = []
        for index, current_line in enumerate(current):
            old_line = previous[index] if index < len(previous) else {}
            old_price = old_line.get("applied_unit_price")
            new_price = current_line.get("applied_unit_price")
            old_version = old_line.get("price_version")
            new_version = current_line.get("price_version")
            if old_price != new_price or old_version != new_version:
                changes.append(
                    {
                        "product_id": current_line.get("product_id"),
                        "product_name": current_line.get("product_name"),
                        "old_unit_price": old_price,
                        "new_unit_price": new_price,
                        "old_price_version": old_version,
                        "new_price_version": new_version,
                    }
                )
        if (draft.pricing_snapshot or {}).get("total_amount") != result.snapshot().get("total_amount"):
            changes.append(
                {
                    "kind": "total",
                    "old_total": (draft.pricing_snapshot or {}).get("total_amount"),
                    "new_total": result.snapshot().get("total_amount"),
                }
            )
        return changes

    async def _availability_changes(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        location_id: uuid.UUID,
        result: PricingResult,
    ) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        for line in result.lines:
            if line.product.product_type in {"menu_item", "raw_material"}:
                continue
            balance = await self.db.scalar(
                select(StockBalance).where(
                    StockBalance.company_id == company_id,
                    StockBalance.branch_id == branch_id,
                    StockBalance.location_id == location_id,
                    StockBalance.product_id == line.product.id,
                    (
                        StockBalance.variant_id.is_(None)
                        if line.variant is None
                        else StockBalance.variant_id == line.variant.id
                    ),
                )
            )
            available = Decimal(balance.qty_available if balance is not None else 0)
            requested = Decimal(line.request.qty)
            if available < requested:
                changes.append(
                    {
                        "kind": "availability",
                        "product_id": str(line.product.id),
                        "product_name": line.product.name,
                        "requested_qty": str(requested),
                        "available_qty": str(available),
                    }
                )
        return changes

    async def _validate_shift(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        shift_id: uuid.UUID,
        location_id: uuid.UUID,
    ) -> CashierShift:
        shift = await self.db.scalar(
            select(CashierShift).where(
                CashierShift.id == shift_id,
                CashierShift.company_id == company_id,
                CashierShift.branch_id == branch_id,
                CashierShift.user_id == user_id,
                CashierShift.location_id == location_id,
                CashierShift.status == "open",
            ).with_for_update()
        )
        if shift is None:
            raise hold_error(
                status.HTTP_409_CONFLICT,
                "draft_shift_invalid",
                "An open shift for the current user, Branch and location is required",
            )
        return shift

    async def _ttl_minutes(self, company_id: uuid.UUID, branch_id: uuid.UUID) -> int:
        settings = await self.db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company_id,
                BranchSettings.branch_id == branch_id,
            )
        )
        value = int(getattr(settings, "pos_hold_draft_ttl_minutes", DEFAULT_DRAFT_TTL_MINUTES) or DEFAULT_DRAFT_TTL_MINUTES)
        return min(max(value, 15), 1440)

    async def _validate_source_context(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        source_type: str,
        table_id: uuid.UUID | None,
    ) -> None:
        if source_type != "restaurant_table":
            if table_id is not None:
                raise hold_error(
                    status.HTTP_409_CONFLICT,
                    "context_mismatch",
                    "table_id is only valid for a Restaurant table Hold Draft",
                )
            return
        if table_id is None:
            raise hold_error(
                status.HTTP_409_CONFLICT,
                "context_mismatch",
                "A Restaurant table Hold Draft requires table_id",
            )
        table = await self.db.scalar(
            select(DiningTable).where(
                DiningTable.id == table_id,
                DiningTable.company_id == company_id,
                DiningTable.branch_id == branch_id,
                DiningTable.is_active.is_(True),
            )
        )
        if table is None:
            raise hold_error(status.HTTP_404_NOT_FOUND, "table_not_found", "Dining table was not found in this Branch")
        if table.status != "available":
            raise hold_error(
                status.HTTP_409_CONFLICT,
                "draft_table_conflict",
                "Dining table is no longer available for this Hold Draft",
                table_status=table.status,
            )

    async def _next_number(self, company_id: uuid.UUID) -> str:
        date_value = datetime.now(timezone.utc).strftime("%Y%m%d")
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"pos-hold:{company_id}:{date_value}"},
        )
        count = await self.db.scalar(
            select(func.count(PosHoldDraft.id)).where(
                PosHoldDraft.company_id == company_id,
                PosHoldDraft.draft_no.like(f"HD{date_value}-%"),
            )
        )
        return f"HD{date_value}-{int(count or 0) + 1:04d}"

    def _audit(
        self,
        draft: PosHoldDraft,
        *,
        actor_user_id: uuid.UUID,
        device_id: uuid.UUID | None,
        shift_id: uuid.UUID | None,
        action: str,
        from_status: str | None,
        from_version: int | None,
        idempotency_key: str,
        request_hash: str,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            PosHoldDraftAudit(
                draft_id=draft.id,
                company_id=draft.company_id,
                branch_id=draft.branch_id,
                actor_user_id=actor_user_id,
                device_id=device_id,
                shift_id=shift_id,
                action=action,
                from_status=from_status,
                to_status=draft.status,
                from_version=from_version,
                to_version=draft.version,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                reason=reason,
                metadata_json=metadata or {},
            )
        )

    async def _operation_replay(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        action: str,
        idempotency_key: str,
        request_hash: str,
    ) -> PosHoldDraft | None:
        audit = await self.db.scalar(
            select(PosHoldDraftAudit).where(
                PosHoldDraftAudit.company_id == company_id,
                PosHoldDraftAudit.branch_id == branch_id,
                PosHoldDraftAudit.action == action,
                PosHoldDraftAudit.idempotency_key == idempotency_key,
            )
        )
        if audit is None:
            return None
        if audit.actor_user_id != actor_user_id:
            raise hold_error(
                status.HTTP_409_CONFLICT,
                "duplicate_request",
                "Idempotency key belongs to another user operation",
            )
        if audit.request_hash != request_hash:
            raise hold_error(
                status.HTTP_409_CONFLICT,
                "duplicate_request",
                "Idempotency key was already used with a different Hold Draft request",
            )
        return await self.db.get(PosHoldDraft, audit.draft_id)

    async def _lock_draft(
        self,
        draft_id: uuid.UUID,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
    ) -> PosHoldDraft:
        draft = await self.db.scalar(
            select(PosHoldDraft)
            .where(
                PosHoldDraft.id == draft_id,
                PosHoldDraft.company_id == company_id,
                PosHoldDraft.brand_id == brand_id,
                PosHoldDraft.branch_id == branch_id,
            )
            .with_for_update()
        )
        if draft is None:
            raise hold_error(status.HTTP_404_NOT_FOUND, "draft_not_found", "Hold Draft was not found")
        return draft

    def _expire_if_needed(self, draft: PosHoldDraft, now: datetime) -> str | None:
        if draft.status in ACTIVE_STATUSES and draft.expires_at <= now:
            draft.status = "expired"
            draft.expired_at = now
            draft.claim_id = None
            draft.claimed_by = None
            draft.claimed_device_id = None
            draft.claim_expires_at = None
            draft.version += 1
            return "expire"
        if draft.status == "claimed" and draft.claim_expires_at is not None and draft.claim_expires_at <= now:
            draft.status = "active"
            draft.claim_id = None
            draft.claimed_by = None
            draft.claimed_device_id = None
            draft.claim_expires_at = None
            draft.version += 1
            return "claim_expire"
        return None

    @staticmethod
    def _assert_version(draft: PosHoldDraft, expected_version: int) -> None:
        if draft.version != expected_version:
            raise hold_error(
                status.HTTP_409_CONFLICT,
                "draft_conflict",
                "Hold Draft changed on another device; refresh before continuing",
                expected_version=expected_version,
                current_version=draft.version,
                current_status=draft.status,
                claimed_by=str(draft.claimed_by) if draft.claimed_by else None,
            )

    async def create(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        device_id: uuid.UUID | None,
        device_code: str | None,
        payload: HoldDraftCreateRequest,
        parent_draft_id: uuid.UUID | None = None,
    ) -> HoldDraftRead:
        request_value = payload.model_dump(mode="json")
        request_hash = canonical_hash(
            {
                "company_id": str(company_id),
                "brand_id": str(brand_id) if brand_id else None,
                "branch_id": str(branch_id),
                "user_id": str(user_id),
                **request_value,
            }
        )
        existing = await self.db.scalar(
            select(PosHoldDraft).where(
                PosHoldDraft.company_id == company_id,
                PosHoldDraft.branch_id == branch_id,
                PosHoldDraft.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise hold_error(status.HTTP_409_CONFLICT, "duplicate_request", "Idempotency key belongs to another Hold Draft payload")
            return self._read(existing)

        await self._validate_shift(
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
            shift_id=payload.shift_id,
            location_id=payload.location_id,
        )
        await self._validate_source_context(
            company_id=company_id,
            branch_id=branch_id,
            source_type=payload.source_type,
            table_id=payload.table_id,
        )
        pricing = await self._calculate(
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            source_type=payload.source_type,
            items=payload.items,
            order_discount=payload.order_discount,
            loyalty_discount=payload.loyalty_discount_intent,
            customer_id=payload.customer_id,
            currency=payload.currency,
            cart_version=payload.cart_version,
            operation_key=f"{payload.idempotency_key}:price",
        )
        ttl = await self._ttl_minutes(company_id, branch_id)
        now = datetime.now(timezone.utc)
        cart = self._cart_snapshot(pricing)
        draft = PosHoldDraft(
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            location_id=payload.location_id,
            origin_shift_id=payload.shift_id,
            owner_user_id=user_id,
            assignee_user_id=user_id,
            origin_device_id=device_id,
            origin_device_code=device_code,
            parent_draft_id=parent_draft_id,
            draft_no=await self._next_number(company_id),
            label=payload.label.strip(),
            source_type=payload.source_type,
            table_id=payload.table_id,
            queue_label=payload.queue_label,
            customer_id=payload.customer_id,
            customer_display=payload.customer_display,
            note=payload.note,
            content_json={
                **cart,
                "pricing_items": [item.model_dump(mode="json") for item in payload.items],
                "order_discount": str(payload.order_discount),
                "loyalty_discount_intent": str(payload.loyalty_discount_intent),
                "currency": payload.currency.upper(),
                "cart_version": payload.cart_version,
            },
            pricing_context=pricing.context(),
            pricing_snapshot=pricing.snapshot(),
            status="active",
            version=1,
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            expires_at=now + timedelta(minutes=ttl),
        )
        self.db.add(draft)
        await self.db.flush()
        self._audit(
            draft,
            actor_user_id=user_id,
            device_id=device_id,
            shift_id=payload.shift_id,
            action="create",
            from_status=None,
            from_version=None,
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            metadata={"item_count": len(payload.items), "ttl_minutes": ttl},
        )
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            replay = await self.db.scalar(
                select(PosHoldDraft).where(
                    PosHoldDraft.company_id == company_id,
                    PosHoldDraft.branch_id == branch_id,
                    PosHoldDraft.idempotency_key == payload.idempotency_key,
                )
            )
            if replay is not None and replay.request_hash == request_hash:
                return self._read(replay)
            raise hold_error(status.HTTP_409_CONFLICT, "duplicate_request", "Hold Draft create conflicted with another request") from exc
        await self.db.refresh(draft)
        return self._read(draft)

    async def list(
        self,
        *,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        status_value: str | None,
        owner_user_id: uuid.UUID | None,
        device_id: uuid.UUID | None,
        search: str | None,
        include_history: bool,
    ) -> list[HoldDraftRead]:
        filters = [
            PosHoldDraft.company_id == company_id,
            PosHoldDraft.brand_id == brand_id,
            PosHoldDraft.branch_id == branch_id,
        ]
        if status_value:
            filters.append(PosHoldDraft.status == status_value)
        elif not include_history:
            filters.append(PosHoldDraft.status.in_(("active", "claimed")))
        if owner_user_id:
            filters.append(PosHoldDraft.owner_user_id == owner_user_id)
        if device_id:
            filters.append(PosHoldDraft.origin_device_id == device_id)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    PosHoldDraft.draft_no.ilike(pattern),
                    PosHoldDraft.label.ilike(pattern),
                    PosHoldDraft.customer_display.ilike(pattern),
                )
            )
        rows = list(
            (
                await self.db.scalars(
                    select(PosHoldDraft)
                    .where(*filters)
                    .order_by(PosHoldDraft.updated_at.desc())
                    .limit(100)
                )
            ).all()
        )
        changed = False
        now = datetime.now(timezone.utc)
        for draft in rows:
            from_status, from_version = draft.status, draft.version
            expiry_action = self._expire_if_needed(draft, now)
            if expiry_action:
                changed = True
                self._audit(
                    draft,
                    actor_user_id=draft.owner_user_id,
                    device_id=None,
                    shift_id=draft.origin_shift_id,
                    action=expiry_action,
                    from_status=from_status,
                    from_version=from_version,
                    idempotency_key=f"expire:{draft.id}:{from_version}",
                    request_hash=canonical_hash({"draft_id": str(draft.id), "version": from_version}),
                )
        if changed:
            await self.db.commit()
            for row in rows:
                await self.db.refresh(row)
        if not include_history and status_value is None:
            rows = [row for row in rows if row.status in ACTIVE_STATUSES]
        return [self._read(row) for row in rows]

    async def get(self, *, draft_id: uuid.UUID, company_id: uuid.UUID, brand_id: uuid.UUID | None, branch_id: uuid.UUID) -> HoldDraftRead:
        draft = await self._lock_draft(draft_id, company_id, brand_id, branch_id)
        from_status, from_version = draft.status, draft.version
        expiry_action = self._expire_if_needed(draft, datetime.now(timezone.utc))
        if expiry_action:
            self._audit(
                draft,
                actor_user_id=draft.owner_user_id,
                device_id=None,
                shift_id=draft.origin_shift_id,
                action=expiry_action,
                from_status=from_status,
                from_version=from_version,
                idempotency_key=f"expire:{draft.id}:{from_version}",
                request_hash=canonical_hash({"draft_id": str(draft.id), "version": from_version}),
            )
            await self.db.commit()
            await self.db.refresh(draft)
        return self._read(draft)

    async def claim(
        self,
        *,
        draft_id: uuid.UUID,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        device_id: uuid.UUID | None,
        payload: HoldDraftActionRequest,
    ) -> HoldDraftClaimRead:
        if payload.shift_id is None or payload.location_id is None:
            raise hold_error(status.HTTP_400_BAD_REQUEST, "draft_shift_invalid", "shift_id and location_id are required")
        request_hash = canonical_hash({"draft_id": str(draft_id), "action": "claim", **payload.model_dump(mode="json")})
        replay = await self._operation_replay(
            company_id=company_id,
            branch_id=branch_id,
            actor_user_id=user_id,
            action="claim",
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
        )
        draft = replay or await self._lock_draft(draft_id, company_id, brand_id, branch_id)
        if draft.brand_id != brand_id:
            raise hold_error(status.HTTP_404_NOT_FOUND, "draft_not_found", "Hold Draft was not found")
        if replay is None:
            from_status, from_version = draft.status, draft.version
            expiry_action = self._expire_if_needed(draft, datetime.now(timezone.utc))
            if expiry_action:
                self._audit(
                    draft,
                    actor_user_id=user_id,
                    device_id=device_id,
                    shift_id=payload.shift_id,
                    action=expiry_action,
                    from_status=from_status,
                    from_version=from_version,
                    idempotency_key=f"{expiry_action}:{draft.id}:{from_version}",
                    request_hash=canonical_hash({"draft_id": str(draft.id), "version": from_version}),
                )
                await self.db.commit()
                raise hold_error(
                    status.HTTP_409_CONFLICT,
                    "draft_conflict",
                    "Hold Draft lifecycle changed; refresh before continuing",
                    current_version=draft.version,
                    current_status=draft.status,
                )
            self._assert_version(draft, payload.expected_version)
            if draft.status != "active":
                raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Hold Draft is not available to resume", current_status=draft.status)
            await self._validate_shift(
                company_id=company_id,
                branch_id=branch_id,
                user_id=user_id,
                shift_id=payload.shift_id,
                location_id=payload.location_id,
            )
            await self._validate_source_context(
                company_id=company_id,
                branch_id=branch_id,
                source_type=draft.source_type,
                table_id=draft.table_id,
            )
            items = self._stored_pricing_items(draft.content_json)
            pricing = await self._calculate(
                company_id=company_id,
                brand_id=draft.brand_id,
                branch_id=branch_id,
                source_type=draft.source_type,
                items=items,
                order_discount=Decimal(draft.content_json.get("order_discount", "0")),
                loyalty_discount=Decimal(draft.content_json.get("loyalty_discount_intent", "0")),
                customer_id=draft.customer_id,
                currency=str(draft.content_json.get("currency", "THB")),
                cart_version=int(draft.content_json.get("cart_version", 1)),
                operation_key=f"{payload.idempotency_key}:revalidate",
                lock_prices=True,
            )
            changes = self._price_changes(draft, pricing)
            changes.extend(
                await self._availability_changes(
                    company_id=company_id,
                    branch_id=branch_id,
                    location_id=payload.location_id,
                    result=pricing,
                )
            )
            draft.status = "claimed"
            draft.claim_id = uuid.uuid4()
            draft.claimed_by = user_id
            draft.claimed_device_id = device_id
            draft.claim_expires_at = datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_CLAIM_TTL_SECONDS)
            draft.last_revalidation = {
                "calculation_hash": pricing.calculation_hash,
                "pricing_snapshot": pricing.snapshot(),
                "resume_cart": self._cart_snapshot(pricing),
                "price_changes": changes,
                "revalidated_at": datetime.now(timezone.utc).isoformat(),
            }
            draft.version += 1
            self._audit(
                draft,
                actor_user_id=user_id,
                device_id=device_id,
                shift_id=payload.shift_id,
                action="claim",
                from_status=from_status,
                from_version=from_version,
                idempotency_key=payload.idempotency_key,
                request_hash=request_hash,
                metadata={"price_changes": changes},
            )
            await self.db.commit()
            await self.db.refresh(draft)
        else:
            changes = list((draft.last_revalidation or {}).get("price_changes", []))
            resume_cart = (draft.last_revalidation or {}).get("resume_cart")
            if not resume_cart:
                raise hold_error(
                    status.HTTP_409_CONFLICT,
                    "draft_replay_unavailable",
                    "The original Hold Draft claim response is unavailable; refresh the draft before retrying",
                )
        return HoldDraftClaimRead(
            draft=self._read(draft),
            resume_cart=resume_cart if replay is not None else self._cart_snapshot(pricing),
            price_changes=changes,
            requires_review=bool(changes),
        )

    async def resume(
        self,
        *,
        draft_id: uuid.UUID,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        device_id: uuid.UUID | None,
        payload: HoldDraftActionRequest,
    ) -> HoldDraftRead:
        if payload.claim_id is None:
            raise hold_error(status.HTTP_400_BAD_REQUEST, "draft_claim_required", "claim_id is required")
        if payload.shift_id is None or payload.location_id is None:
            raise hold_error(status.HTTP_400_BAD_REQUEST, "draft_shift_invalid", "shift_id and location_id are required")
        request_hash = canonical_hash({"draft_id": str(draft_id), "action": "resume", **payload.model_dump(mode="json")})
        replay = await self._operation_replay(
            company_id=company_id,
            branch_id=branch_id,
            actor_user_id=user_id,
            action="resume",
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            if replay.brand_id != brand_id:
                raise hold_error(status.HTTP_404_NOT_FOUND, "draft_not_found", "Hold Draft was not found")
            return self._read(replay)
        draft = await self._lock_draft(draft_id, company_id, brand_id, branch_id)
        self._assert_version(draft, payload.expected_version)
        if draft.status != "claimed" or draft.claim_id != payload.claim_id:
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Hold Draft claim is no longer valid", current_status=draft.status)
        if draft.claimed_by != user_id or draft.claimed_device_id != device_id:
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Hold Draft is claimed by another user or Counter")
        if draft.claim_expires_at is None or draft.claim_expires_at <= datetime.now(timezone.utc):
            raise hold_error(status.HTTP_409_CONFLICT, "draft_claim_expired", "Hold Draft claim expired; refresh and retry")
        await self._validate_shift(
            company_id=company_id,
            branch_id=branch_id,
            user_id=user_id,
            shift_id=payload.shift_id,
            location_id=payload.location_id,
        )
        await self._validate_source_context(
            company_id=company_id,
            branch_id=branch_id,
            source_type=draft.source_type,
            table_id=draft.table_id,
        )
        pricing = await self._calculate(
            company_id=company_id,
            brand_id=draft.brand_id,
            branch_id=branch_id,
            source_type=draft.source_type,
            items=self._stored_pricing_items(draft.content_json),
            order_discount=Decimal(draft.content_json.get("order_discount", "0")),
            loyalty_discount=Decimal(draft.content_json.get("loyalty_discount_intent", "0")),
            customer_id=draft.customer_id,
            currency=str(draft.content_json.get("currency", "THB")),
            cart_version=int(draft.content_json.get("cart_version", 1)),
            operation_key=f"{payload.idempotency_key}:resume",
            lock_prices=True,
        )
        changes = self._price_changes(draft, pricing)
        changes.extend(
            await self._availability_changes(
                company_id=company_id,
                branch_id=branch_id,
                location_id=payload.location_id or draft.location_id,
                result=pricing,
            )
        )
        if changes and not payload.accept_revalidation:
            raise hold_error(
                status.HTTP_409_CONFLICT,
                "draft_revalidation_required",
                "Price or catalog context changed; explicit acceptance is required",
                price_changes=changes,
            )
        from_status, from_version = draft.status, draft.version
        draft.status = "resumed"
        draft.resumed_at = datetime.now(timezone.utc)
        draft.resumed_by = user_id
        draft.resumed_device_id = device_id
        draft.claim_expires_at = None
        draft.pricing_context = pricing.context()
        draft.last_revalidation = {
            "calculation_hash": pricing.calculation_hash,
            "pricing_snapshot": pricing.snapshot(),
            "price_changes": changes,
            "accepted": payload.accept_revalidation,
            "revalidated_at": datetime.now(timezone.utc).isoformat(),
        }
        draft.version += 1
        self._audit(
            draft,
            actor_user_id=user_id,
            device_id=device_id,
            shift_id=payload.shift_id,
            action="resume",
            from_status=from_status,
            from_version=from_version,
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            metadata={"price_changes": changes, "accepted": payload.accept_revalidation},
        )
        await self.db.commit()
        await self.db.refresh(draft)
        return self._read(draft)

    async def release_claim(
        self,
        *,
        draft_id: uuid.UUID,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        device_id: uuid.UUID | None,
        payload: HoldDraftActionRequest,
    ) -> HoldDraftRead:
        request_hash = canonical_hash({"draft_id": str(draft_id), "action": "release", **payload.model_dump(mode="json")})
        replay = await self._operation_replay(company_id=company_id, branch_id=branch_id, actor_user_id=user_id, action="release", idempotency_key=payload.idempotency_key, request_hash=request_hash)
        if replay is not None:
            if replay.brand_id != brand_id:
                raise hold_error(status.HTTP_404_NOT_FOUND, "draft_not_found", "Hold Draft was not found")
            return self._read(replay)
        draft = await self._lock_draft(draft_id, company_id, brand_id, branch_id)
        self._assert_version(draft, payload.expected_version)
        if draft.status != "claimed" or draft.claim_id != payload.claim_id or draft.claimed_by != user_id:
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Hold Draft claim cannot be released by this context")
        from_status, from_version = draft.status, draft.version
        draft.status = "active"
        draft.claim_id = None
        draft.claimed_by = None
        draft.claimed_device_id = None
        draft.claim_expires_at = None
        draft.version += 1
        self._audit(draft, actor_user_id=user_id, device_id=device_id, shift_id=payload.shift_id, action="release", from_status=from_status, from_version=from_version, idempotency_key=payload.idempotency_key, request_hash=request_hash, reason=payload.reason)
        await self.db.commit()
        await self.db.refresh(draft)
        return self._read(draft)

    async def discard(
        self,
        *,
        draft_id: uuid.UUID,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        device_id: uuid.UUID | None,
        payload: HoldDraftActionRequest,
    ) -> HoldDraftRead:
        if not payload.reason or len(payload.reason.strip()) < 3:
            raise hold_error(status.HTTP_400_BAD_REQUEST, "draft_reason_required", "Discard reason must contain at least 3 characters")
        request_hash = canonical_hash({"draft_id": str(draft_id), "action": "discard", **payload.model_dump(mode="json")})
        replay = await self._operation_replay(company_id=company_id, branch_id=branch_id, actor_user_id=user_id, action="discard", idempotency_key=payload.idempotency_key, request_hash=request_hash)
        if replay is not None:
            if replay.brand_id != brand_id:
                raise hold_error(status.HTTP_404_NOT_FOUND, "draft_not_found", "Hold Draft was not found")
            return self._read(replay)
        draft = await self._lock_draft(draft_id, company_id, brand_id, branch_id)
        self._assert_version(draft, payload.expected_version)
        if draft.status not in ACTIVE_STATUSES:
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Only active Hold Drafts can be cancelled", current_status=draft.status)
        if draft.status == "claimed" and draft.claimed_by != user_id:
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Hold Draft is being opened by another user")
        from_status, from_version = draft.status, draft.version
        draft.status = "cancelled"
        draft.cancelled_at = datetime.now(timezone.utc)
        draft.cancelled_by = user_id
        draft.cancel_reason = payload.reason.strip()
        draft.claim_id = None
        draft.claimed_by = None
        draft.claimed_device_id = None
        draft.claim_expires_at = None
        draft.version += 1
        self._audit(draft, actor_user_id=user_id, device_id=device_id, shift_id=payload.shift_id, action="discard", from_status=from_status, from_version=from_version, idempotency_key=payload.idempotency_key, request_hash=request_hash, reason=draft.cancel_reason)
        await self.db.commit()
        await self.db.refresh(draft)
        return self._read(draft)

    async def update(
        self,
        *,
        draft_id: uuid.UUID,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        device_id: uuid.UUID | None,
        payload: HoldDraftUpdateRequest,
        can_reassign: bool,
    ) -> HoldDraftRead:
        request_hash = canonical_hash({"draft_id": str(draft_id), "action": "update", **payload.model_dump(mode="json")})
        replay = await self._operation_replay(company_id=company_id, branch_id=branch_id, actor_user_id=user_id, action="update", idempotency_key=payload.idempotency_key, request_hash=request_hash)
        if replay is not None:
            if replay.brand_id != brand_id:
                raise hold_error(status.HTTP_404_NOT_FOUND, "draft_not_found", "Hold Draft was not found")
            return self._read(replay)
        draft = await self._lock_draft(draft_id, company_id, brand_id, branch_id)
        self._assert_version(draft, payload.expected_version)
        if draft.status != "active":
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Only active Hold Drafts can be updated", current_status=draft.status)
        reassigned = payload.assignee_user_id != draft.assignee_user_id and payload.assignee_user_id is not None
        if reassigned:
            if not can_reassign:
                raise hold_error(status.HTTP_403_FORBIDDEN, "permission_denied", "Permission required: pos.draft.reassign")
            if not payload.reason or len(payload.reason.strip()) < 3:
                raise hold_error(status.HTTP_400_BAD_REQUEST, "draft_reason_required", "Reassign reason must contain at least 3 characters")
            assignee = await self.db.scalar(
                select(User)
                .join(UserBranch, UserBranch.user_id == User.id)
                .where(
                    User.id == payload.assignee_user_id,
                    User.company_id == company_id,
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                    UserBranch.branch_id == branch_id,
                    UserBranch.brand_id == brand_id,
                    UserBranch.deleted_at.is_(None),
                )
            )
            if assignee is None:
                raise hold_error(status.HTTP_409_CONFLICT, "context_mismatch", "Assignee is not active in this Brand and Branch")
            draft.assignee_user_id = assignee.id
        if payload.label is not None:
            draft.label = payload.label.strip()
        if payload.note is not None:
            draft.note = payload.note
        if payload.items is not None:
            order_discount = payload.order_discount if payload.order_discount is not None else Decimal(draft.content_json.get("order_discount", "0"))
            loyalty_discount = payload.loyalty_discount_intent if payload.loyalty_discount_intent is not None else Decimal(draft.content_json.get("loyalty_discount_intent", "0"))
            cart_version = payload.cart_version if payload.cart_version is not None else int(draft.content_json.get("cart_version", 1)) + 1
            pricing = await self._calculate(
                company_id=company_id,
                brand_id=brand_id,
                branch_id=branch_id,
                source_type=draft.source_type,
                items=payload.items,
                order_discount=order_discount,
                loyalty_discount=loyalty_discount,
                customer_id=draft.customer_id,
                currency=str(draft.content_json.get("currency", "THB")),
                cart_version=cart_version,
                operation_key=f"{payload.idempotency_key}:price",
                lock_prices=True,
            )
            draft.content_json = {
                **self._cart_snapshot(pricing),
                "pricing_items": [item.model_dump(mode="json") for item in payload.items],
                "order_discount": str(order_discount),
                "loyalty_discount_intent": str(loyalty_discount),
                "currency": str(draft.content_json.get("currency", "THB")),
                "cart_version": cart_version,
            }
            draft.pricing_context = pricing.context()
            draft.pricing_snapshot = pricing.snapshot()
        from_status, from_version = draft.status, draft.version
        draft.version += 1
        self._audit(
            draft,
            actor_user_id=user_id,
            device_id=device_id,
            shift_id=draft.origin_shift_id,
            action="update",
            from_status=from_status,
            from_version=from_version,
            idempotency_key=payload.idempotency_key,
            request_hash=request_hash,
            reason=payload.reason.strip() if payload.reason else None,
            metadata={"reassigned": reassigned, "assignee_user_id": str(draft.assignee_user_id) if reassigned else None},
        )
        await self.db.commit()
        await self.db.refresh(draft)
        return self._read(draft)

    async def reopen(
        self,
        *,
        draft_id: uuid.UUID,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        device_id: uuid.UUID | None,
        device_code: str | None,
        payload: HoldDraftActionRequest,
    ) -> HoldDraftRead:
        if payload.shift_id is None or payload.location_id is None:
            raise hold_error(status.HTTP_400_BAD_REQUEST, "draft_shift_invalid", "shift_id and location_id are required")
        source = await self._lock_draft(draft_id, company_id, brand_id, branch_id)
        if source.status == "converted":
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "A converted Hold Draft cannot be reopened")
        if source.status not in {"resumed", "expired", "cancelled"}:
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Only resumed, expired or cancelled Hold Drafts can be reopened")
        self._assert_version(source, payload.expected_version)
        content = source.content_json
        create_payload = HoldDraftCreateRequest(
            shift_id=payload.shift_id,
            location_id=payload.location_id,
            label=f"{source.label} (กู้คืน)",
            source_type=source.source_type,
            table_id=source.table_id,
            queue_label=source.queue_label,
            customer_id=source.customer_id,
            customer_display=source.customer_display,
            note=source.note,
            items=self._stored_pricing_items(content),
            order_discount=Decimal(content.get("order_discount", "0")),
            loyalty_discount_intent=Decimal(content.get("loyalty_discount_intent", "0")),
            currency=str(content.get("currency", "THB")),
            cart_version=int(content.get("cart_version", 1)) + 1,
            idempotency_key=payload.idempotency_key,
        )
        source_id = source.id
        await self.db.rollback()
        return await self.create(
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            user_id=user_id,
            device_id=device_id,
            device_code=device_code,
            payload=create_payload,
            parent_draft_id=source_id,
        )

    async def convert_into_sale(
        self,
        *,
        draft_id: uuid.UUID,
        expected_version: int,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        order_id: uuid.UUID,
    ) -> None:
        draft = await self._lock_draft(draft_id, company_id, brand_id, branch_id)
        if draft.status == "converted" and draft.converted_order_id == order_id:
            return
        self._assert_version(draft, expected_version)
        if draft.status != "resumed" or draft.resumed_by != user_id:
            raise hold_error(status.HTTP_409_CONFLICT, "draft_conflict", "Hold Draft must be resumed by the current user before checkout", current_status=draft.status)
        from_status, from_version = draft.status, draft.version
        draft.status = "converted"
        draft.converted_order_id = order_id
        draft.converted_at = datetime.now(timezone.utc)
        draft.version += 1
        request_hash = canonical_hash({"draft_id": str(draft_id), "order_id": str(order_id), "version": expected_version})
        self._audit(
            draft,
            actor_user_id=user_id,
            device_id=draft.resumed_device_id,
            shift_id=draft.origin_shift_id,
            action="convert",
            from_status=from_status,
            from_version=from_version,
            idempotency_key=f"sale:{order_id}",
            request_hash=request_hash,
            metadata={"order_id": str(order_id)},
        )

    async def count_pending_for_shift(self, shift_id: uuid.UUID) -> int:
        now = datetime.now(timezone.utc)
        shift = await self.db.get(CashierShift, shift_id)
        if shift is None:
            return 0
        return int(
            await self.db.scalar(
                select(func.count(PosHoldDraft.id)).where(
                    PosHoldDraft.origin_shift_id == shift_id,
                    PosHoldDraft.status.in_(("active", "claimed")),
                    PosHoldDraft.expires_at > now,
                    or_(
                        PosHoldDraft.assignee_user_id.is_(None),
                        PosHoldDraft.assignee_user_id == shift.user_id,
                    ),
                )
            )
            or 0
        )
