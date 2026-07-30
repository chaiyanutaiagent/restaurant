from __future__ import annotations

from typing import Any
import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import TokenData, require_permission
from app.schemas.payment_gateway import (
    CreateOmiseRequest,
    CreatePromptPayRequest,
    GatewayConfigRead,
    GatewayConfigUpdate,
    NotificationLogRead,
    NotificationTestRequest,
    PaymentSessionConfirmRequest,
    PaymentSessionRead,
)
from app.services.notification_service import NotificationService
from app.services.payment_gateway_service import PaymentGatewayService

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


def ok(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"data": data, "meta": {"version": settings.app_version, **(meta or {})}, "error": None}


@router.get("/config")
async def get_config(
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await PaymentGatewayService(db).get_config(current.company_id)
    return ok(GatewayConfigRead.model_validate(row).model_dump(mode="json"))


@router.patch("/config")
async def update_config(
    payload: GatewayConfigUpdate,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await PaymentGatewayService(db).update_config(
        current.company_id,
        payload.model_dump(exclude_unset=True),
    )
    return ok(GatewayConfigRead.model_validate(row).model_dump(mode="json"))


@router.post("/config/test-line")
async def test_line_notify(
    payload: NotificationTestRequest,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await PaymentGatewayService(db).get_config_decrypted(current.company_id)
    if not config.line_notify_token:
        return ok({"success": False, "message": "Line Notify token is not configured"})
    success = await NotificationService(db).send_line_notify(
        config.line_notify_token,
        payload.message or "🔔 ทดสอบการแจ้งเตือน Restaurant POS — เชื่อมต่อสำเร็จ",
        current.company_id,
        "system.test.line",
    )
    await db.commit()
    return ok({"success": success})


@router.post("/config/test-email")
async def test_email(
    payload: NotificationTestRequest,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = await PaymentGatewayService(db).get_config_decrypted(current.company_id)
    recipient = payload.recipient or config.smtp_from_email
    if not recipient:
        return ok({"success": False, "message": "SMTP recipient is not configured"})
    success = await NotificationService(db).send_email(
        config,
        recipient,
        "ทดสอบ Email Restaurant POS",
        "<h2>🔔 ทดสอบการแจ้งเตือน Restaurant POS</h2><p>เชื่อมต่อสำเร็จ</p>",
        current.company_id,
        "system.test.email",
    )
    await db.commit()
    return ok({"success": success})


@router.get("/sessions")
async def list_sessions(
    status_value: str | None = None,
    gateway: str | None = None,
    page: int = 1,
    limit: int = 20,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await PaymentGatewayService(db).list_sessions(
        current.company_id,
        status_value=status_value,
        gateway=gateway,
        page=page,
        limit=limit,
    )
    data = [PaymentSessionRead.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(data, meta={"total": total, "page": page, "limit": limit})


@router.post("/sessions/promptpay", status_code=status.HTTP_201_CREATED)
async def create_promptpay_session(
    payload: CreatePromptPayRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await PaymentGatewayService(db).create_promptpay_session(
        current.company_id,
        payload.branch_id,
        payload.amount,
        payload.reference_type,
        payload.reference_id,
        current.user_id,
    )
    return ok(PaymentSessionRead.model_validate(row).model_dump(mode="json"))


@router.post("/sessions/omise", status_code=status.HTTP_201_CREATED)
async def create_omise_session(
    payload: CreateOmiseRequest,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await PaymentGatewayService(db).create_omise_session(
        current.company_id,
        payload.branch_id,
        payload.amount,
        payload.method,
        payload.reference_type,
        payload.reference_id,
        current.user_id,
    )
    return ok(PaymentSessionRead.model_validate(row).model_dump(mode="json"))


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await PaymentGatewayService(db).get_session(session_id, current.company_id)
    return ok(PaymentSessionRead.model_validate(row).model_dump(mode="json"))


@router.post("/sessions/{session_id}/check")
async def check_session(
    session_id: uuid.UUID,
    current: TokenData = Depends(require_permission("pos.sale.view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await PaymentGatewayService(db).check_payment_status(session_id, current.company_id)
    return ok(PaymentSessionRead.model_validate(row).model_dump(mode="json"))


@router.post("/sessions/{session_id}/confirm")
async def confirm_session(
    session_id: uuid.UUID,
    payload: PaymentSessionConfirmRequest | None = None,
    current: TokenData = Depends(require_permission("pos.sale.create")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    row = await PaymentGatewayService(db).confirm_payment(
        session_id,
        current.company_id,
        payload.gateway_ref if payload else None,
    )
    return ok(PaymentSessionRead.model_validate(row).model_dump(mode="json"))


@router.post("/callback/omise")
async def omise_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    payload = await request.json()
    company_id_raw = payload.get("company_id") or payload.get("key")
    if not company_id_raw:
        return ok({"updated": False})
    row = await PaymentGatewayService(db).handle_gateway_callback(uuid.UUID(str(company_id_raw)), "omise", payload)
    return ok({"updated": row is not None, "session_id": str(row.id) if row else None})


@router.post("/callback/2c2p")
async def twoc2p_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    payload = await request.json()
    company_id_raw = payload.get("company_id") or payload.get("merchant_id")
    if not company_id_raw:
        return ok({"updated": False})
    row = await PaymentGatewayService(db).handle_gateway_callback(uuid.UUID(str(company_id_raw)), "2c2p", payload)
    return ok({"updated": row is not None, "session_id": str(row.id) if row else None})


@router.get("/notifications")
async def list_notifications(
    page: int = 1,
    limit: int = 50,
    current: TokenData = Depends(require_permission("system.company.edit")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await PaymentGatewayService(db).list_notification_logs(
        current.company_id,
        page=page,
        limit=limit,
    )
    data = [NotificationLogRead.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(data, meta={"total": total, "page": page, "limit": limit})
