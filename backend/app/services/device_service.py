from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from urllib.parse import urlencode
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import TokenData
from app.models.audit import AuditLog
from app.models.device import DeviceRegistration
from app.models.settings import BranchSettings
from app.schemas.device import (
    DeviceActionReason,
    DeviceContextRead,
    DeviceCreate,
    DevicePairRead,
    DevicePairRequest,
    DeviceProvisioningRead,
    DeviceRead,
)
from app.services.business_context_service import load_branch_business_context
from app.services.staff_scope_policy import normalized_station_key
from app.utils.security import (
    create_device_access_token,
    decode_token,
    hash_password,
    verify_password,
)


DEVICE_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def invalid_pairing_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired device pairing credentials",
    )


class DeviceService:
    def __init__(self, db: AsyncSession, *, restaurant_db: AsyncSession | None = None):
        self.db = db
        self.restaurant_db = restaurant_db or db

    async def list_devices(
        self,
        current: TokenData,
        *,
        branch_id: uuid.UUID | None = None,
    ) -> list[DeviceRead]:
        effective_branch_id = branch_id
        company_wide = "*" in current.permissions or "company" in current.scope_types
        if not company_wide:
            if current.branch_id is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Branch context is required to view devices",
                )
            if branch_id is not None and branch_id != current.branch_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
            effective_branch_id = current.branch_id

        statement = select(DeviceRegistration).where(
            DeviceRegistration.company_id == current.company_id
        )
        if effective_branch_id is not None:
            statement = statement.where(DeviceRegistration.branch_id == effective_branch_id)
        rows = (
            await self.db.scalars(
                statement.order_by(
                    DeviceRegistration.revoked_at.asc().nulls_first(),
                    DeviceRegistration.created_at.desc(),
                )
            )
        ).all()
        return [self._read(row) for row in rows]

    async def create_device(
        self,
        current: TokenData,
        data: DeviceCreate,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> DeviceProvisioningRead:
        self._require_branch_access(current, data.branch_id)
        context = await self._restaurant_context(current.company_id, data.branch_id)
        station_key = await self._canonical_station(
            current.company_id,
            data.branch_id,
            data.device_type,
            data.station_key,
        )
        pairing_pin, pairing_expires_at = self._new_pairing_credential()
        device = DeviceRegistration(
            company_id=current.company_id,
            branch_id=context.branch_id,
            device_code=await self._new_device_code(current.company_id, data.device_type),
            name=data.name,
            device_type=data.device_type,
            station_key=station_key,
            pairing_pin_hash=hash_password(pairing_pin),
            pairing_expires_at=pairing_expires_at,
            credential_version=1,
            created_by=current.user_id,
        )
        self.db.add(device)
        await self.db.flush()
        self._audit(
            device=device,
            actor_id=current.user_id,
            action="system.device.create",
            reason=data.reason,
            old_value=None,
            new_value=self._snapshot(device, reason=data.reason),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(device)
        return self._provisioning(device, pairing_pin, pairing_expires_at)

    async def rotate_pairing_code(
        self,
        current: TokenData,
        device_id: uuid.UUID,
        data: DeviceActionReason,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> DeviceProvisioningRead:
        device = await self._get_device(current.company_id, device_id, for_update=True)
        self._require_branch_access(current, device.branch_id)
        if device.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Revoked devices cannot receive a new pairing code",
            )
        await self._restaurant_context(current.company_id, device.branch_id)
        await self._canonical_station(
            current.company_id,
            device.branch_id,
            device.device_type,
            device.station_key,
        )

        old_value = self._snapshot(device, reason=data.reason)
        pairing_pin, pairing_expires_at = self._new_pairing_credential()
        device.pairing_pin_hash = hash_password(pairing_pin)
        device.pairing_expires_at = pairing_expires_at
        device.failed_pairing_attempts = 0
        device.pairing_locked_until = None
        device.credential_version += 1
        device.paired_at = None
        device.last_seen_at = None
        self._audit(
            device=device,
            actor_id=current.user_id,
            action="system.device.pairing.rotate",
            reason=data.reason,
            old_value=old_value,
            new_value=self._snapshot(device, reason=data.reason),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(device)
        return self._provisioning(device, pairing_pin, pairing_expires_at)

    async def revoke_device(
        self,
        current: TokenData,
        device_id: uuid.UUID,
        data: DeviceActionReason,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> DeviceRead:
        device = await self._get_device(current.company_id, device_id, for_update=True)
        self._require_branch_access(current, device.branch_id)
        if device.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

        old_value = self._snapshot(device, reason=data.reason)
        device.revoked_by = current.user_id
        device.revoked_at = datetime.now(timezone.utc)
        device.revocation_reason = data.reason
        device.credential_version += 1
        device.pairing_pin_hash = None
        device.pairing_expires_at = None
        device.pairing_locked_until = None
        self._audit(
            device=device,
            actor_id=current.user_id,
            action="system.device.revoke",
            reason=data.reason,
            old_value=old_value,
            new_value=self._snapshot(device, reason=data.reason),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        await self.db.refresh(device)
        return self._read(device)

    async def pair_device(
        self,
        data: DevicePairRequest,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> DevicePairRead:
        device = await self.db.scalar(
            select(DeviceRegistration).where(
                DeviceRegistration.company_id == data.company_id,
                DeviceRegistration.device_code == data.device_code,
            ).with_for_update()
        )
        now = datetime.now(timezone.utc)
        if device is None or device.revoked_at is not None:
            raise invalid_pairing_credentials()
        if device.pairing_locked_until is not None and device.pairing_locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Device pairing is temporarily locked",
            )
        if device.pairing_locked_until is not None:
            device.failed_pairing_attempts = 0
            device.pairing_locked_until = None
        if (
            device.pairing_pin_hash is None
            or device.pairing_expires_at is None
            or device.pairing_expires_at <= now
        ):
            raise invalid_pairing_credentials()
        if not verify_password(data.pairing_pin, device.pairing_pin_hash):
            device.failed_pairing_attempts += 1
            if device.failed_pairing_attempts >= settings.device_pairing_max_failed_attempts:
                device.pairing_locked_until = now + timedelta(
                    minutes=settings.device_pairing_lock_minutes
                )
            await self.db.commit()
            if device.pairing_locked_until is not None:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Device pairing is temporarily locked",
                )
            raise invalid_pairing_credentials()

        try:
            context = await self._restaurant_context(device.company_id, device.branch_id)
            await self._canonical_station(
                device.company_id,
                device.branch_id,
                device.device_type,
                device.station_key,
            )
        except HTTPException as exc:
            raise invalid_pairing_credentials() from exc

        old_value = self._snapshot(device, reason="successful pairing")
        device.pairing_pin_hash = None
        device.pairing_expires_at = None
        device.failed_pairing_attempts = 0
        device.pairing_locked_until = None
        device.paired_at = now
        device.last_seen_at = now
        access_token = create_device_access_token(
            device_id=device.id,
            company_id=device.company_id,
            brand_id=context.brand_id,
            branch_id=device.branch_id,
            device_type=device.device_type,
            station_key=device.station_key,
            credential_version=device.credential_version,
        )
        self._audit(
            device=device,
            actor_id=None,
            action="device.pair",
            reason="successful pairing",
            old_value=old_value,
            new_value=self._snapshot(device, reason="successful pairing"),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await self.db.commit()
        token_payload = decode_token(access_token)
        expires_in = max(int(token_payload["exp"] - now.timestamp()), 0)
        return DevicePairRead(
            access_token=access_token,
            expires_in=expires_in,
            device=DeviceContextRead(
                device_id=device.id,
                company_id=device.company_id,
                brand_id=context.brand_id,
                branch_id=device.branch_id,
                device_code=device.device_code,
                name=device.name,
                device_type=device.device_type,
                station_key=device.station_key,
                business_type="restaurant",
                target_database="restaurant",
                credential_version=device.credential_version,
                paired_at=now,
                last_seen_at=now,
            ),
        )

    async def _get_device(
        self,
        company_id: uuid.UUID,
        device_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> DeviceRegistration:
        statement = select(DeviceRegistration).where(
            DeviceRegistration.id == device_id,
            DeviceRegistration.company_id == company_id,
        )
        if for_update:
            statement = statement.with_for_update()
        device = await self.db.scalar(statement)
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
        return device

    async def _restaurant_context(self, company_id: uuid.UUID, branch_id: uuid.UUID):
        context = await load_branch_business_context(self.db, company_id, branch_id)
        if (
            context is None
            or context.business_type != "restaurant"
            or context.target_database != "restaurant"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Devices in this scope require a Restaurant Branch",
            )
        return context

    async def _canonical_station(
        self,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        device_type: str,
        station_key: str | None,
    ) -> str | None:
        if device_type != "kitchen":
            return None
        settings_row = await self.restaurant_db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company_id,
                BranchSettings.branch_id == branch_id,
            )
        )
        requested = normalized_station_key(station_key)
        configured_stations = settings_row.fb_kitchen_stations if settings_row else []
        for configured in configured_stations or []:
            if normalized_station_key(configured) == requested:
                return str(configured).strip()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kitchen station is not configured for this Branch",
        )

    @staticmethod
    def _require_branch_access(current: TokenData, branch_id: uuid.UUID) -> None:
        if "*" in current.permissions or "company" in current.scope_types:
            return
        if current.branch_id == branch_id:
            return
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")

    async def _new_device_code(self, company_id: uuid.UUID, device_type: str) -> str:
        prefix = {"counter": "C", "kitchen": "K", "pickup": "P"}[device_type]
        for _ in range(10):
            suffix = "".join(secrets.choice(DEVICE_CODE_ALPHABET) for _ in range(10))
            candidate = f"{prefix}-{suffix}"
            exists = await self.db.scalar(
                select(DeviceRegistration.id).where(
                    DeviceRegistration.company_id == company_id,
                    DeviceRegistration.device_code == candidate,
                )
            )
            if exists is None:
                return candidate
        raise RuntimeError("Could not allocate a unique device code")

    @staticmethod
    def _new_pairing_credential() -> tuple[str, datetime]:
        pin = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.device_pairing_pin_expire_minutes
        )
        return pin, expires_at

    def _provisioning(
        self,
        device: DeviceRegistration,
        pairing_pin: str,
        pairing_expires_at: datetime,
    ) -> DeviceProvisioningRead:
        query = urlencode(
            {
                "company_id": str(device.company_id),
                "device_code": device.device_code,
                "pin": pairing_pin,
            }
        )
        return DeviceProvisioningRead(
            device=self._read(device),
            pairing_pin=pairing_pin,
            pairing_expires_at=pairing_expires_at,
            pairing_qr_payload=f"restaurant-pos://pair?{query}",
        )

    @staticmethod
    def _status(device: DeviceRegistration) -> str:
        if device.revoked_at is not None:
            return "revoked"
        if device.paired_at is not None and device.pairing_pin_hash is None:
            return "paired"
        if (
            device.pairing_pin_hash is not None
            and device.pairing_expires_at is not None
            and device.pairing_expires_at > datetime.now(timezone.utc)
        ):
            return "pending_pairing"
        return "pairing_expired"

    def _read(self, device: DeviceRegistration) -> DeviceRead:
        return DeviceRead(
            id=device.id,
            company_id=device.company_id,
            branch_id=device.branch_id,
            device_code=device.device_code,
            name=device.name,
            device_type=device.device_type,
            station_key=device.station_key,
            status=self._status(device),
            credential_version=device.credential_version,
            pairing_expires_at=device.pairing_expires_at,
            paired_at=device.paired_at,
            last_seen_at=device.last_seen_at,
            revoked_at=device.revoked_at,
            revocation_reason=device.revocation_reason,
            created_at=device.created_at,
            updated_at=device.updated_at,
        )

    @staticmethod
    def _snapshot(device: DeviceRegistration, *, reason: str) -> dict:
        return {
            "device_code": device.device_code,
            "name": device.name,
            "device_type": device.device_type,
            "branch_id": str(device.branch_id),
            "station_key": device.station_key,
            "credential_version": device.credential_version,
            "paired_at": device.paired_at.isoformat() if device.paired_at else None,
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
            "revoked_at": device.revoked_at.isoformat() if device.revoked_at else None,
            "reason": reason,
        }

    def _audit(
        self,
        *,
        device: DeviceRegistration,
        actor_id: uuid.UUID | None,
        action: str,
        reason: str,
        old_value: dict | None,
        new_value: dict,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.db.add(
            AuditLog(
                company_id=device.company_id,
                branch_id=device.branch_id,
                user_id=actor_id,
                action=action,
                resource="DeviceRegistration",
                resource_id=str(device.id),
                old_value=old_value,
                new_value={**new_value, "reason": reason},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
