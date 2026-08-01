from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import DeviceTokenData, TokenData
from app.models.device import DeviceRegistration
from app.schemas.restaurant import WapOfflinePaidOrderRequest
from app.utils.security import (
    create_offline_sale_authorization,
    decode_offline_sale_authorization,
)


OFFLINE_POLICY_VERSION = 1
CLOCK_SKEW = timedelta(minutes=5)


class OfflineSaleAuthorizationService:
    @staticmethod
    def issue(
        current: TokenData,
        *,
        shift_id: uuid.UUID | None,
        location_id: uuid.UUID | None,
        brand_id: uuid.UUID | None,
        device: DeviceTokenData | None,
    ) -> tuple[str, datetime]:
        if current.branch_id is None:
            raise ValueError("Branch context required")
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=settings.offline_sale_authorization_expire_hours
        )
        token = create_offline_sale_authorization(
            user_id=current.user_id,
            company_id=current.company_id,
            branch_id=current.branch_id,
            shift_id=shift_id,
            location_id=location_id,
            brand_id=brand_id,
            device_id=device.device_id if device else None,
            device_credential_version=device.credential_version if device else None,
            expires_delta=expires_at - datetime.now(timezone.utc),
        )
        return token, expires_at

    @staticmethod
    async def validate(
        identity_db: AsyncSession,
        current: TokenData,
        payload: WapOfflinePaidOrderRequest,
        *,
        brand_id: uuid.UUID | None,
    ) -> None:
        if payload.offline_policy_version is None and payload.offline_authorization is None:
            # Rollout compatibility for orders durably queued by versions before this policy.
            return
        if (
            payload.offline_policy_version != OFFLINE_POLICY_VERSION
            or not payload.offline_authorization
            or payload.local_created_at is None
        ):
            raise ValueError("สิทธิ์ขายออฟไลน์ไม่ครบ กรุณาให้ผู้จัดการตรวจสอบรายการ")
        try:
            claims = decode_offline_sale_authorization(payload.offline_authorization)
        except HTTPException as exc:
            raise ValueError("สิทธิ์ขายออฟไลน์ไม่ถูกต้อง") from exc
        if claims.get("type") != "offline_sale_authorization" or claims.get("policy_version") != 1:
            raise ValueError("นโยบายสิทธิ์ขายออฟไลน์ไม่ถูกต้อง")

        expected = {
            "sub": str(current.user_id),
            "company_id": str(current.company_id),
            "branch_id": str(current.branch_id),
            "shift_id": str(payload.shift_id) if payload.shift_id else None,
            "location_id": str(payload.location_id) if payload.location_id else None,
            "brand_id": str(brand_id) if brand_id else None,
        }
        if any(claims.get(key) != value for key, value in expected.items()):
            raise ValueError("สิทธิ์ขายออฟไลน์ไม่ตรงกับพนักงาน สาขา กะ หรือคลัง")

        try:
            issued_at = datetime.fromtimestamp(float(claims["iat"]), timezone.utc)
            expires_at = datetime.fromtimestamp(float(claims["exp"]), timezone.utc)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("ช่วงเวลาสิทธิ์ขายออฟไลน์ไม่ถูกต้อง") from exc
        local_created_at = payload.local_created_at
        if local_created_at.tzinfo is None:
            local_created_at = local_created_at.replace(tzinfo=timezone.utc)
        if (
            local_created_at < issued_at - CLOCK_SKEW
            or local_created_at > expires_at
            or local_created_at > datetime.now(timezone.utc) + CLOCK_SKEW
        ):
            raise ValueError("รายการถูกสร้างนอกช่วงเวลาที่อนุญาตให้ขายออฟไลน์")

        device_id_value = claims.get("device_id")
        if device_id_value is None:
            return
        try:
            device_id = uuid.UUID(device_id_value)
            credential_version = int(claims["device_credential_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("ข้อมูลอุปกรณ์ในสิทธิ์ขายออฟไลน์ไม่ถูกต้อง") from exc
        device = await identity_db.get(DeviceRegistration, device_id)
        if (
            device is None
            or device.company_id != current.company_id
            or device.branch_id != current.branch_id
            or device.device_type != "counter"
            or device.station_key is not None
            or device.paired_at is None
            or device.paired_at > local_created_at
            or credential_version < 1
            or (device.revoked_at is not None and device.revoked_at <= local_created_at)
        ):
            raise ValueError("อุปกรณ์ไม่มีสิทธิ์สำหรับรายการขายออฟไลน์นี้")
