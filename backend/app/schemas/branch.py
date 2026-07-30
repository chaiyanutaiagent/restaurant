from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import ConfigDict

from app.schemas import BaseSchema


class BranchBase(BaseSchema):
    company_id: uuid.UUID
    code: str
    name: str
    address: str | None = None
    landmark: str | None = None
    phone: str | None = None
    email: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_url: str | None = None
    is_warehouse: bool = False
    is_active: bool = True
    sort_order: int = 0


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseSchema):
    company_id: uuid.UUID | None = None
    code: str | None = None
    name: str | None = None
    address: str | None = None
    landmark: str | None = None
    phone: str | None = None
    email: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    google_maps_url: str | None = None
    is_warehouse: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class BranchRead(BranchBase):
    id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
