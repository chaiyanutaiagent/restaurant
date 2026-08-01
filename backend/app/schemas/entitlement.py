from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import Field

from app.schemas import BaseSchema


class BrandModuleEntitlementUpdate(BaseSchema):
    is_enabled: bool
    config: dict[str, object] = Field(default_factory=dict)


class BrandModuleEntitlementRead(BaseSchema):
    id: uuid.UUID | None = None
    company_id: uuid.UUID
    brand_id: uuid.UUID
    module_key: str
    is_enabled: bool
    config: dict[str, object] = Field(default_factory=dict)
    changed_by: uuid.UUID | None = None
    changed_at: datetime | None = None
