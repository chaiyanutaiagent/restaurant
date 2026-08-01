from __future__ import annotations

from dataclasses import dataclass
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import TokenData
from app.models.restaurant import Brand, BrandBranch
from app.models.stock import StockLocation


CENTRAL_RAW_VIEW_PERMISSIONS = {
    "brand.central.raw_stock.view",
    "brand.central.raw_stock.manage",
    "brand.central.production.view",
    "brand.central.production.manage",
}
CENTRAL_READY_VIEW_PERMISSIONS = {
    "brand.central.ready_stock.view",
    "brand.central.ready_stock.manage",
    "brand.central.production.view",
    "brand.central.production.manage",
}
CENTRAL_RAW_MANAGE_PERMISSIONS = {"brand.central.raw_stock.manage"}
CENTRAL_READY_MANAGE_PERMISSIONS = {"brand.central.ready_stock.manage"}
CENTRAL_STOCK_PERMISSIONS = (
    CENTRAL_RAW_VIEW_PERMISSIONS | CENTRAL_READY_VIEW_PERMISSIONS
)
STORE_STOCK_VIEW_PERMISSIONS = {
    "brand.store.stock.view",
    "brand.store.stock.adjust",
}
STORE_STOCK_MANAGE_PERMISSIONS = {
    "brand.store.stock.adjust",
    "inventory.stock.adjust.request",
}

STOCK_VIEW_PERMISSIONS = (
    "inventory.stock.view",
    "inventory.stock.adjust",
    "inventory.stock.adjust.request",
    "brand.store.stock.view",
    "brand.store.stock.adjust",
    "brand.central.raw_stock.view",
    "brand.central.raw_stock.manage",
    "brand.central.ready_stock.view",
    "brand.central.ready_stock.manage",
    "brand.central.production.view",
    "brand.central.production.manage",
)
STOCK_MANAGE_PERMISSIONS = (
    "inventory.stock.adjust",
    "brand.store.stock.adjust",
    "brand.central.raw_stock.manage",
    "brand.central.ready_stock.manage",
)


@dataclass(frozen=True)
class StockAccessScope:
    branch_id: uuid.UUID | None
    location_ids: tuple[uuid.UUID, ...] | None


def has_central_stock_access(current: TokenData) -> bool:
    return "*" in current.permissions or bool(
        CENTRAL_STOCK_PERMISSIONS.intersection(current.permissions)
    )


class StockAccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_scope(
        self,
        current: TokenData,
        requested_branch_id: uuid.UUID | None = None,
        requested_location_id: uuid.UUID | None = None,
        *,
        manage: bool = False,
    ) -> StockAccessScope:
        if "*" in current.permissions:
            return StockAccessScope(
                branch_id=requested_branch_id,
                location_ids=(requested_location_id,) if requested_location_id else None,
            )

        branch_id = self.require_current_branch(current, requested_branch_id)
        location_ids = await self._accessible_location_ids(
            current,
            branch_id,
            manage=manage,
        )
        if requested_location_id is not None:
            if requested_location_id not in location_ids:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Stock location not found",
                )
            location_ids = (requested_location_id,)
        return StockAccessScope(branch_id=branch_id, location_ids=location_ids)

    def require_current_branch(
        self,
        current: TokenData,
        requested_branch_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        if current.branch_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Branch context required for stock access",
            )
        if requested_branch_id is not None and requested_branch_id != current.branch_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Branch not found",
            )
        return current.branch_id

    async def _accessible_location_ids(
        self,
        current: TokenData,
        branch_id: uuid.UUID,
        *,
        manage: bool,
    ) -> tuple[uuid.UUID, ...]:
        all_location_ids = tuple(
            (
                await self.db.scalars(
                    select(StockLocation.id).where(
                        StockLocation.company_id == current.company_id,
                        StockLocation.branch_id == branch_id,
                        StockLocation.deleted_at.is_(None),
                        StockLocation.is_active.is_(True),
                    )
                )
            ).all()
        )
        brand_rows = (
            await self.db.execute(
                select(
                    Brand.id,
                    Brand.central_branch_id,
                    Brand.central_location_id,
                    Brand.central_ready_location_id,
                ).where(
                    Brand.company_id == current.company_id,
                    Brand.is_active.is_(True),
                )
            )
        ).all()
        # A configured READY location is the cutover marker for strict
        # separation. Legacy brands may still map the same location as both
        # central and store stock, so excluding RAW before cutover would make
        # their store balance disappear immediately after this migration.
        separated_central_location_ids = {
            location_id
            for _, _, raw_location_id, ready_location_id in brand_rows
            for location_id in (raw_location_id, ready_location_id)
            if ready_location_id is not None and location_id is not None
        }

        raw_permissions = (
            CENTRAL_RAW_MANAGE_PERMISSIONS
            if manage
            else CENTRAL_RAW_VIEW_PERMISSIONS
        )
        ready_permissions = (
            CENTRAL_READY_MANAGE_PERMISSIONS
            if manage
            else CENTRAL_READY_VIEW_PERMISSIONS
        )
        can_access_raw = bool(raw_permissions.intersection(current.permissions))
        can_access_ready = bool(ready_permissions.intersection(current.permissions))
        allowed_location_ids: set[uuid.UUID] = set()
        if can_access_raw or can_access_ready:
            for brand_id, central_branch_id, raw_location_id, ready_location_id in brand_rows:
                if current.brand_id is not None and brand_id != current.brand_id:
                    continue
                if central_branch_id != branch_id:
                    continue
                if can_access_raw and raw_location_id is not None:
                    allowed_location_ids.add(raw_location_id)
                if can_access_ready and ready_location_id is not None:
                    allowed_location_ids.add(ready_location_id)

        store_permissions = (
            STORE_STOCK_MANAGE_PERMISSIONS
            if manage
            else STORE_STOCK_VIEW_PERMISSIONS
        )
        has_store_permission = bool(
            store_permissions.intersection(current.permissions)
        )
        # A role may legitimately cover both central and store stock (for
        # example Company Owner). Do not let central permissions hide the
        # store location of a retail-only brand that has no central warehouse.
        if has_store_permission or not (can_access_raw or can_access_ready):
            store_statement = select(BrandBranch.store_location_id).where(
                BrandBranch.company_id == current.company_id,
                BrandBranch.branch_id == branch_id,
                BrandBranch.is_active.is_(True),
                BrandBranch.store_location_id.is_not(None),
            )
            if current.brand_id is not None:
                store_statement = store_statement.where(
                    BrandBranch.brand_id == current.brand_id
                )
            store_location_ids = set(
                (await self.db.scalars(store_statement)).all()
            )
            use_store_mapping = current.brand_id is not None or has_store_permission
            allowed_store_ids = (
                store_location_ids
                if use_store_mapping
                else set(all_location_ids)
            )
            allowed_location_ids.update(
                location_id
                for location_id in allowed_store_ids
                if location_id not in separated_central_location_ids
            )

        return tuple(
            location_id
            for location_id in all_location_ids
            if location_id in allowed_location_ids
        )
