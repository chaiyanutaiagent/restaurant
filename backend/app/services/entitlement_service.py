from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_context import RESTAURANT
from app.models.audit import AuditLog
from app.models.entitlement import BrandModuleEntitlement
from app.models.restaurant import Brand
from app.schemas.entitlement import BrandModuleEntitlementRead


CENTRAL_PRODUCTION_MODULE = "restaurant.central_production"


class EntitlementService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_brand_module(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        module_key: str,
    ) -> BrandModuleEntitlementRead:
        await self._get_restaurant_brand(company_id, brand_id)
        row = await self.db.scalar(
            select(BrandModuleEntitlement).where(
                BrandModuleEntitlement.company_id == company_id,
                BrandModuleEntitlement.brand_id == brand_id,
                BrandModuleEntitlement.module_key == module_key,
            )
        )
        if row is None:
            return BrandModuleEntitlementRead(
                company_id=company_id,
                brand_id=brand_id,
                module_key=module_key,
                is_enabled=False,
            )
        return BrandModuleEntitlementRead.model_validate(row, from_attributes=True)

    async def set_brand_module(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        module_key: str,
        *,
        is_enabled: bool,
        config: dict[str, object],
        actor_id: uuid.UUID,
    ) -> BrandModuleEntitlementRead:
        await self._get_restaurant_brand(company_id, brand_id)
        previous = await self.get_brand_module(company_id, brand_id, module_key)
        changed_at = datetime.now(timezone.utc)
        row_id = (
            await self.db.execute(
                insert(BrandModuleEntitlement)
                .values(
                    id=uuid.uuid4(),
                    company_id=company_id,
                    brand_id=brand_id,
                    module_key=module_key,
                    is_enabled=is_enabled,
                    config=config,
                    changed_by=actor_id,
                    changed_at=changed_at,
                )
                .on_conflict_do_update(
                    constraint="uq_brand_module_entitlements_scope_module",
                    set_={
                        "is_enabled": is_enabled,
                        "config": config,
                        "changed_by": actor_id,
                        "changed_at": changed_at,
                    },
                )
                .returning(BrandModuleEntitlement.id)
            )
        ).scalar_one()
        self.db.add(
            AuditLog(
                company_id=company_id,
                user_id=actor_id,
                action="system.brand_module_entitlement.update",
                resource="BrandModuleEntitlement",
                resource_id=str(row_id),
                old_value=previous.model_dump(mode="json"),
                new_value={
                    "brand_id": str(brand_id),
                    "module_key": module_key,
                    "is_enabled": is_enabled,
                    "config": config,
                },
            )
        )
        await self.db.commit()
        return await self.get_brand_module(company_id, brand_id, module_key)

    async def require_brand_module_enabled(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
        module_key: str,
    ) -> None:
        entitlement = await self.get_brand_module(company_id, brand_id, module_key)
        if not entitlement.is_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "module_disabled",
                    "module_key": module_key,
                    "message": "Module is not enabled for this Brand",
                },
            )

    async def _get_restaurant_brand(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID,
    ) -> Brand:
        brand = await self.db.scalar(
            select(Brand).where(
                Brand.id == brand_id,
                Brand.company_id == company_id,
                Brand.business_type == RESTAURANT,
                Brand.is_active.is_(True),
            )
        )
        if brand is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant Brand not found")
        return brand
