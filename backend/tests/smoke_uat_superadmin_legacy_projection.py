from __future__ import annotations

import asyncio
from decimal import Decimal
import json
import os

from sqlalchemy import func, select, text

from app.config import settings
from app.database import AsyncSessionLocal, PlatformSessionLocal
from app.models.stock import StockLocation
from app.models.user import User
from app.schemas.pos import OpenShiftRequest
from app.services.auth_service import AuthService
from app.services.sale_service import SaleService


DATABASE_PREFIX = "uat_fix_"


async def _database_name(session) -> str:
    return str(await session.scalar(func.current_database()) or "")


async def main() -> None:
    if os.environ.get("UAT_SUPERADMIN_CLONE_SMOKE") != "1":
        raise RuntimeError("UAT superadmin smoke requires its explicit clone-only gate")
    if (
        settings.identity_database != "platform_core"
        or settings.restaurant_service_database != "legacy"
    ):
        raise RuntimeError("UAT superadmin smoke requires Platform identity and legacy operations")

    async with PlatformSessionLocal() as platform, AsyncSessionLocal() as legacy:
        platform_database = await _database_name(platform)
        legacy_database = await _database_name(legacy)
        if not platform_database.startswith(DATABASE_PREFIX):
            raise RuntimeError("UAT superadmin smoke refuses a non-clone Platform database")
        if not legacy_database.startswith(DATABASE_PREFIX):
            raise RuntimeError("UAT superadmin smoke refuses a non-clone legacy database")
        if platform_database == legacy_database:
            raise RuntimeError("UAT superadmin smoke requires separate Platform and legacy clones")

        user = await platform.scalar(
            select(User).where(
                User.company_id == settings.uat_superadmin_company_id,
                func.lower(User.username) == settings.uat_superadmin_username.strip().lower(),
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                User.is_superuser.is_(True),
            )
        )
        if user is None:
            raise RuntimeError("Configured UAT superadmin is missing from the Platform clone")

        legacy_user_before = await legacy.scalar(select(User.id).where(User.id == user.id))
        if legacy_user_before is not None:
            raise RuntimeError(
                "Clone no longer reproduces the missing legacy operational user prerequisite"
            )

        candidate_branch_ids = list(
            (
                await platform.scalars(
                    text(
                        """
                        SELECT DISTINCT branch.id
                        FROM branches AS branch
                        JOIN brand_branches AS assignment
                          ON assignment.branch_id = branch.id
                         AND assignment.company_id = branch.company_id
                        JOIN brands AS brand
                          ON brand.id = assignment.brand_id
                         AND brand.company_id = branch.company_id
                        WHERE branch.company_id = :company_id
                          AND branch.deleted_at IS NULL
                          AND branch.is_active IS TRUE
                          AND assignment.is_active IS TRUE
                          AND brand.is_active IS TRUE
                          AND brand.business_type = 'restaurant'
                        ORDER BY branch.id
                        """
                    ),
                    {"company_id": user.company_id},
                )
            ).all()
        )
        if not candidate_branch_ids:
            raise RuntimeError("Platform clone has no active Restaurant branch for the UAT company")

        location = await legacy.scalar(
            select(StockLocation)
            .where(
                StockLocation.company_id == user.company_id,
                StockLocation.branch_id.in_(candidate_branch_ids),
                StockLocation.deleted_at.is_(None),
                StockLocation.is_active.is_(True),
            )
            .order_by(StockLocation.branch_id, StockLocation.code)
            .limit(1)
        )
        if location is None:
            raise RuntimeError("Legacy clone has no active Restaurant stock location")
        branch_id = location.branch_id
        location_id = location.id

        access_token, refresh_token = await AuthService(
            platform,
            emit_reference_events=True,
        ).create_session(
            user,
            branch_id,
            "127.0.0.1",
            "uat-superadmin-clone-smoke",
            station_key="counter-1",
        )
        if not access_token or not refresh_token:
            raise RuntimeError("UAT superadmin session credentials were not issued")

        await legacy.rollback()
        mirrored_user = await legacy.scalar(select(User).where(User.id == user.id))
        if mirrored_user is None:
            raise RuntimeError("UAT superadmin was not mirrored into legacy operations")
        if mirrored_user.company_id != user.company_id or mirrored_user.username != user.username:
            raise RuntimeError("Mirrored UAT superadmin identity does not match Platform")

        shift = await SaleService(legacy).open_shift(
            user.company_id,
            branch_id,
            user.id,
            OpenShiftRequest(
                location_id=location_id,
                opening_cash=Decimal("0"),
                idempotency_key="uat-superadmin-clone-smoke-v1",
            ),
            device_code="clone-smoke",
            ip_address="127.0.0.1",
            user_agent="uat-superadmin-clone-smoke",
        )
        if shift.user_id != user.id:
            raise RuntimeError("Shift audit actor differs from the Platform UAT superadmin")

        print(
            json.dumps(
                {
                    "status": "PASS",
                    "platform_database": platform_database,
                    "legacy_database": legacy_database,
                    "company_id": str(user.company_id),
                    "branch_id": str(branch_id),
                    "location_id": str(location_id),
                    "user_id": str(user.id),
                    "shift_id": str(shift.id),
                    "shift_number": shift.shift_number,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
