from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any
import uuid

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import TokenData
from app.models.approval import ApprovalGrantUsage, ManagerPinCredential
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.approval import (
    ApprovalAction,
    ApprovalSessionRead,
    ApprovalSessionRequest,
    ManagerPinSetRequest,
    ManagerPinStatusRead,
)
from app.schemas.pos import (
    CreateSaleRequest,
    PartialRefundRequest,
    RefundRequest,
    VoidRequest,
)
from app.schemas.stock import AdjustmentRequest
from app.schemas.restaurant import RestaurantCancellationRequest, SessionCheckoutRequest
from app.services.auth_service import AuthService
from app.utils.security import (
    create_approval_token,
    decode_token,
    hash_password,
    verify_password,
)


DIRECT_PERMISSION_BY_ACTION: dict[str, str] = {
    "pos.discount.override": "pos.discount.override",
    "pos.price.override": "pos.price.override",
    "pos.sale.void": "pos.sale.void",
    "pos.refund.create": "pos.refund.create",
    "inventory.stock.adjust": "inventory.stock.adjust",
    "fb.order.cancel_after_kitchen": "fb.order.cancel.approve",
    "fb.order.cancel.reopen": "fb.order.cancel.reopen",
}

REQUEST_PERMISSION_BY_ACTION: dict[str, str] = {
    "pos.discount.override": "pos.discount.apply",
    "pos.price.override": "pos.price.override.request",
    "pos.sale.void": "pos.sale.void.request",
    "pos.refund.create": "pos.refund.request",
    "inventory.stock.adjust": "inventory.stock.adjust.request",
    "fb.order.cancel_after_kitchen": "fb.order.cancel.request",
    "fb.order.cancel.reopen": "fb.order.cancel.reopen.request",
}


def has_permission(permissions: list[str], code: str) -> bool:
    return "*" in permissions or code in permissions


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, uuid.UUID, Decimal)):
        return str(value)
    raise TypeError(f"Unsupported approval payload value: {type(value).__name__}")


def approval_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_approval_request_payload(
    action: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    values = dict(payload)
    order_id = values.pop("order_id", None)
    try:
        if action in {"pos.discount.override", "pos.price.override"}:
            session_id = values.pop("session_id", None)
            schema = SessionCheckoutRequest if session_id is not None else CreateSaleRequest
            normalized = schema.model_validate(values).model_dump(
                mode="json",
                exclude={"approval_token", "price_override_approval_token"},
                exclude_none=True,
                exclude_unset=True,
            )
            if session_id is not None:
                normalized["session_id"] = str(uuid.UUID(str(session_id)))
        elif action == "pos.sale.void":
            normalized = VoidRequest.model_validate(values).model_dump(
                mode="json",
                exclude={"approval_token"},
                exclude_none=True,
                exclude_unset=True,
            )
        elif action == "pos.refund.create":
            schema = PartialRefundRequest if "items" in values else RefundRequest
            normalized = schema.model_validate(values).model_dump(
                mode="json",
                exclude={"approval_token"},
                exclude_none=True,
                exclude_unset=True,
            )
        elif action == "inventory.stock.adjust":
            normalized = AdjustmentRequest.model_validate(values).model_dump(
                mode="json",
                exclude={"approval_token"},
                exclude_none=True,
                exclude_unset=True,
            )
        elif action == "fb.order.cancel_after_kitchen":
            normalized = RestaurantCancellationRequest.model_validate(values).model_dump(
                mode="json",
                exclude={"approval_token"},
                exclude_none=True,
            )
        elif action == "fb.order.cancel.reopen":
            cancellation_id = values.get("cancellation_id")
            idempotency_key = str(values.get("idempotency_key") or "").strip()
            reason = str(values.get("reason") or "").strip()
            if cancellation_id is None or not (8 <= len(idempotency_key) <= 100) or not (3 <= len(reason) <= 500):
                raise ValueError("Invalid cancellation reopen approval payload")
            normalized = {
                "cancellation_id": str(uuid.UUID(str(cancellation_id))),
                "idempotency_key": idempotency_key,
                "reason": reason,
            }
        else:
            raise ValueError("Unsupported approval action")
        if action in {"pos.sale.void", "pos.refund.create"}:
            if order_id is None:
                raise ValueError("order_id is required for this approval action")
            normalized["order_id"] = str(uuid.UUID(str(order_id)))
        return normalized
    except (ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approval request payload is invalid for this action",
        ) from exc


@dataclass(frozen=True)
class ApprovalEvidence:
    action: str
    requester_id: uuid.UUID
    approver_id: uuid.UUID
    reason: str
    mode: str
    grant_id: uuid.UUID | None = None
    request_hash: str | None = None

    def as_audit_value(self) -> dict[str, str | None]:
        return {
            "action": self.action,
            "requester_id": str(self.requester_id),
            "approver_id": str(self.approver_id),
            "reason": self.reason,
            "mode": self.mode,
            "grant_id": str(self.grant_id) if self.grant_id else None,
            "request_hash": self.request_hash,
        }


class ApprovalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_manager_pin_status(
        self,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ManagerPinStatusRead:
        credential = await self.db.scalar(
            select(ManagerPinCredential).where(
                ManagerPinCredential.company_id == company_id,
                ManagerPinCredential.user_id == user_id,
            )
        )
        return ManagerPinStatusRead(
            is_set=credential is not None,
            pin_set_at=credential.pin_set_at if credential else None,
            locked_until=credential.locked_until if credential else None,
        )

    async def set_manager_pin(
        self,
        *,
        current: TokenData,
        user: User,
        data: ManagerPinSetRequest,
        ip_address: str | None,
        user_agent: str | None,
    ) -> ManagerPinStatusRead:
        if not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect",
            )

        permissions, *_ = await AuthService(self.db).get_user_permissions(
            user,
            current.branch_id,
            current.station_key,
        )
        if not any(
            has_permission(permissions, permission)
            for permission in DIRECT_PERMISSION_BY_ACTION.values()
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="An approval permission is required to set a Manager PIN",
            )

        now = datetime.now(timezone.utc)
        credential = await self.db.scalar(
            select(ManagerPinCredential).where(
                ManagerPinCredential.company_id == current.company_id,
                ManagerPinCredential.user_id == current.user_id,
            )
        )
        was_set = credential is not None
        if credential is None:
            credential = ManagerPinCredential(
                company_id=current.company_id,
                user_id=current.user_id,
                pin_hash=hash_password(data.pin),
                pin_set_at=now,
            )
            self.db.add(credential)
        else:
            credential.pin_hash = hash_password(data.pin)
            credential.failed_attempts = 0
            credential.locked_until = None
            credential.pin_set_at = now

        self.db.add(
            AuditLog(
                company_id=current.company_id,
                branch_id=current.branch_id,
                user_id=current.user_id,
                action="approval.manager_pin.rotate" if was_set else "approval.manager_pin.set",
                resource="ManagerPinCredential",
                resource_id=str(current.user_id),
                old_value={"is_set": was_set},
                new_value={"is_set": True, "pin_set_at": now.isoformat()},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.db.commit()
        return await self.get_manager_pin_status(current.company_id, current.user_id)

    async def create_session(
        self,
        *,
        current: TokenData,
        requester: User,
        data: ApprovalSessionRequest,
        ip_address: str | None,
        user_agent: str | None,
    ) -> ApprovalSessionRead:
        if current.branch_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Select a branch before requesting approval",
            )

        direct_permission = DIRECT_PERMISSION_BY_ACTION[data.action]
        request_permission = REQUEST_PERMISSION_BY_ACTION[data.action]
        requester_permissions, *_ = await AuthService(self.db).get_user_permissions(
            requester,
            current.branch_id,
            current.station_key,
        )
        if not (
            has_permission(requester_permissions, direct_permission)
            or has_permission(requester_permissions, request_permission)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {request_permission}",
            )

        approver = await self.db.scalar(
            select(User).where(
                User.company_id == current.company_id,
                User.username == data.approver_username,
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        )
        if approver is None:
            raise self._invalid_manager_credentials()
        if approver.id == current.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-approval is not allowed",
            )

        approver_permissions, *_ = await AuthService(self.db).get_user_permissions(
            approver,
            current.branch_id,
            current.station_key,
        )
        if not has_permission(approver_permissions, direct_permission):
            raise self._invalid_manager_credentials()

        credential = await self.db.scalar(
            select(ManagerPinCredential)
            .where(
                ManagerPinCredential.company_id == current.company_id,
                ManagerPinCredential.user_id == approver.id,
            )
            .with_for_update()
        )
        if credential is None:
            raise self._invalid_manager_credentials()

        now = datetime.now(timezone.utc)
        if credential.locked_until is not None and credential.locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail={
                    "code": "manager_pin_locked",
                    "message": "Manager PIN is temporarily locked",
                    "locked_until": credential.locked_until.isoformat(),
                },
            )

        if not verify_password(data.manager_pin, credential.pin_hash):
            credential.failed_attempts += 1
            if credential.failed_attempts >= settings.manager_pin_max_failed_attempts:
                credential.locked_until = now + timedelta(
                    minutes=settings.manager_pin_lock_minutes
                )
                credential.failed_attempts = 0
            self._audit_session_attempt(
                current=current,
                approver_id=approver.id,
                action=data.action,
                reason=data.reason,
                outcome="invalid_pin",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self.db.commit()
            raise self._invalid_manager_credentials()

        credential.failed_attempts = 0
        credential.locked_until = None
        grant_id = uuid.uuid4()
        normalized_request = normalize_approval_request_payload(
            data.action,
            data.request_payload,
        )
        request_hash = approval_request_hash(normalized_request)
        approval_token = create_approval_token(
            grant_id=grant_id,
            company_id=current.company_id,
            branch_id=current.branch_id,
            requester_id=current.user_id,
            approver_id=approver.id,
            action=data.action,
            reason=data.reason,
            request_hash=request_hash,
        )
        self._audit_session_attempt(
            current=current,
            approver_id=approver.id,
            action=data.action,
            reason=data.reason,
            outcome="issued",
            grant_id=grant_id,
            request_hash=request_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()

        display_name = approver.display_name or " ".join(
            part for part in (approver.first_name, approver.last_name) if part
        ) or approver.username
        return ApprovalSessionRead(
            approval_token=approval_token,
            expires_in=settings.approval_token_expire_seconds,
            action=data.action,
            approver_id=approver.id,
            approver_display_name=display_name,
            request_hash=request_hash,
        )

    async def authorize_operation(
        self,
        *,
        current: TokenData,
        action: ApprovalAction,
        request_payload: dict[str, Any],
        approval_token: str | None,
        reason: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        allow_direct: bool = True,
    ) -> ApprovalEvidence:
        direct_permission = DIRECT_PERMISSION_BY_ACTION[action]
        if allow_direct and has_permission(current.permissions, direct_permission):
            return ApprovalEvidence(
                action=action,
                requester_id=current.user_id,
                approver_id=current.user_id,
                reason=reason,
                mode="direct_permission",
            )
        if not approval_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "approval_required",
                    "action": action,
                    "message": "Manager approval is required",
                },
            )
        if current.branch_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Select a branch before using approval",
            )

        try:
            claims = decode_token(approval_token)
        except HTTPException as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "expired_approval",
                    "action": action,
                    "message": "Approval is invalid or expired; request a new approval",
                },
            ) from exc
        normalized_request = normalize_approval_request_payload(action, request_payload)
        expected_hash = approval_request_hash(normalized_request)
        try:
            grant_id = uuid.UUID(claims["jti"])
            company_id = uuid.UUID(claims["company_id"])
            branch_id = uuid.UUID(claims["branch_id"])
            requester_id = uuid.UUID(claims["requester_id"])
            approver_id = uuid.UUID(claims["approver_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid approval token",
            ) from exc

        if (
            claims.get("type") != "approval"
            or company_id != current.company_id
            or branch_id != current.branch_id
            or requester_id != current.user_id
            or claims.get("action") != action
            or claims.get("request_hash") != expected_hash
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "approval_mismatch",
                    "action": action,
                    "message": "Approval does not match this request",
                },
            )

        issued_at = datetime.fromtimestamp(claims["iat"], tz=timezone.utc)
        expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
        usage = ApprovalGrantUsage(
            company_id=company_id,
            branch_id=branch_id,
            grant_id=grant_id,
            requester_id=requester_id,
            approver_id=approver_id,
            action=action,
            reason=str(claims["reason"]),
            request_hash=expected_hash,
            resource_type=resource_type,
            resource_id=resource_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        self.db.add(usage)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "approval_already_used",
                    "action": action,
                    "message": "Approval has already been used",
                },
            ) from exc
        return ApprovalEvidence(
            action=action,
            requester_id=requester_id,
            approver_id=approver_id,
            reason=str(claims["reason"]),
            mode="manager_pin",
            grant_id=grant_id,
            request_hash=expected_hash,
        )

    def _audit_session_attempt(
        self,
        *,
        current: TokenData,
        approver_id: uuid.UUID,
        action: str,
        reason: str,
        outcome: str,
        ip_address: str | None,
        user_agent: str | None,
        grant_id: uuid.UUID | None = None,
        request_hash: str | None = None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=current.company_id,
                branch_id=current.branch_id,
                user_id=current.user_id,
                action="approval.session.issue" if outcome == "issued" else "approval.session.deny",
                resource="ApprovalSession",
                resource_id=str(grant_id) if grant_id else None,
                new_value={
                    "requester_id": str(current.user_id),
                    "approver_id": str(approver_id),
                    "action": action,
                    "reason": reason,
                    "outcome": outcome,
                    "request_hash": request_hash,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )

    @staticmethod
    def _invalid_manager_credentials() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid manager credentials",
        )
