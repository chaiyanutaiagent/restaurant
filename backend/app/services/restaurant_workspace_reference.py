"""First-use reference bootstrap while Restaurant operations still use legacy.

Only Platform-owned references are copied, never settings, stock or transactions.
The caller owns the destination transaction, so failed setup rolls back the bridge.
"""
from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import TokenData
from app.models.branch import Branch
from app.services.platform_reference_projection import REFERENCE_COLUMNS, REFERENCE_TABLES

logger = logging.getLogger(__name__)


async def ensure_restaurant_workspace_reference(
    source: AsyncSession, target: AsyncSession, current: TokenData,
) -> None:
    if settings.identity_database != "platform_core" or settings.restaurant_service_database != "legacy":
        return
    existing = await target.scalar(select(Branch).where(Branch.id == current.branch_id))
    if existing is not None:
        if existing.company_id != current.company_id or not existing.is_active or existing.deleted_at:
            raise HTTPException(403, "ไม่มีสิทธิ์ใช้สาขานี้")
        return
    if not current.branch_id or not current.brand_id or current.business_type != "restaurant":
        raise HTTPException(409, "กรุณาเปิดพื้นที่ทำงาน Restaurant และเลือกสาขาก่อนตั้งค่า")

    # Verify the canonical relationship, not client-selected headers or IDs alone.
    link = (await source.execute(text("""
        SELECT bb.id FROM brand_branches bb
        JOIN brands b ON b.id = bb.brand_id AND b.company_id = bb.company_id
        JOIN branches br ON br.id = bb.branch_id AND br.company_id = bb.company_id
        JOIN companies c ON c.id = bb.company_id
        WHERE bb.company_id = :company AND bb.brand_id = :brand AND bb.branch_id = :branch
          AND bb.is_active AND b.is_active AND br.is_active AND c.is_active
          AND br.deleted_at IS NULL AND b.business_type = 'restaurant'
    """), {"company": current.company_id, "brand": current.brand_id, "branch": current.branch_id})).scalar_one_or_none()
    if link is None:
        raise HTTPException(403, "ไม่พบพื้นที่ทำงาน Restaurant ที่เปิดใช้งานและอยู่ในบริษัทนี้")

    async def load(kind, identity):
        row = (await source.execute(text(
            f"SELECT {', '.join(REFERENCE_COLUMNS[kind])} FROM {REFERENCE_TABLES[kind]} WHERE id = :id"
        ), {"id": identity})).mappings().one_or_none()
        if row is None or (row["id"] if kind == "company" else row["company_id"]) != current.company_id:
            raise HTTPException(403, "ข้อมูลอ้างอิงพื้นที่ทำงานไม่ตรงกับบริษัท")
        return dict(row)

    company = await load("company", current.company_id)
    branch = await load("branch", current.branch_id)
    brand = await load("brand", current.brand_id)
    actor = await load("user", current.user_id)
    references = [("company", company), ("branch", branch)]
    if brand["central_branch_id"] and brand["central_branch_id"] != current.branch_id:
        references.append(("branch", await load("branch", brand["central_branch_id"])))
    references.extend([("brand", brand), ("brand_branch", await load("brand_branch", link)), ("user", actor)])
    try:
        async with target.begin_nested():
            for kind, values in references:
                table = REFERENCE_TABLES[kind]
                if kind != "company":
                    owner = (await target.execute(text(f"SELECT company_id FROM {table} WHERE id = :id"), {"id": values["id"]})).scalar_one_or_none()
                    if owner is not None and owner != current.company_id:
                        raise HTTPException(403, "ข้อมูลอ้างอิงสาขาขัดแย้งกับบริษัทอื่น")
                columns = REFERENCE_COLUMNS[kind]
                if kind == "brand":
                    values["theme_config"] = json.dumps(values["theme_config"])
                bindings = ", ".join("CAST(:theme_config AS jsonb)" if c == "theme_config" else f":{c}" for c in columns)
                await target.execute(text(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({bindings}) ON CONFLICT (id) DO NOTHING"
                ), values)
    except SQLAlchemyError as exc:
        logger.warning("Restaurant workspace reference bootstrap failed: %s", type(exc).__name__)
        raise HTTPException(503, "ข้อมูลอ้างอิงสาขายังไม่พร้อม กรุณาลองเปิดพื้นที่ทำงานอีกครั้ง หรือติดต่อผู้ดูแล") from exc
