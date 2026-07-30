from __future__ import annotations

from datetime import datetime
import uuid

from pydantic import ConfigDict

from app.schemas import BaseSchema


class CompanyBase(BaseSchema):
    name: str
    tax_id: str | None = None
    vat_registered: bool = False
    currency: str = "THB"
    timezone: str = "Asia/Bangkok"


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseSchema):
    name: str | None = None
    tax_id: str | None = None
    vat_registered: bool | None = None
    currency: str | None = None
    timezone: str | None = None


class CompanyRead(CompanyBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
