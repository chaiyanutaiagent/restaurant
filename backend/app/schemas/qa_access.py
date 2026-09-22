from __future__ import annotations

from typing import Literal
import uuid

from pydantic import Field

from app.schemas import BaseSchema


class QaPersonaBranchRead(BaseSchema):
    id: uuid.UUID
    name: str
    code: str
    is_default: bool


class QaPersonaRead(BaseSchema):
    key: str
    label: str
    surface: Literal["tenant", "platform", "public"]
    subject_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    company_name: str | None = None
    business_slug: str | None = None
    branches: list[QaPersonaBranchRead] = Field(default_factory=list)


class QaSessionRequest(BaseSchema):
    persona: str = Field(min_length=1, max_length=80)
    branch_id: uuid.UUID | None = None
    station_key: str | None = Field(default=None, max_length=80)
