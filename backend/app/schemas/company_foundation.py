from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from pydantic import Field, field_validator

from app.schemas import BaseSchema
from app.schemas.module_access import CompanyModuleAccessRead, CompanyModuleKey


RuntimeEnvironment = Literal["production", "uat"]
OperationalState = Literal[
    "online",
    "offline",
    "degraded",
    "pending_sync",
    "stale",
    "error",
    "disabled",
]
ErpReadinessState = Literal["ready", "attention", "blocked", "hold", "permission_denied"]
WorkItemSeverity = Literal["info", "warning", "error", "blocker"]
WorkItemStatus = Literal["open", "acknowledged", "completed", "dismissed"]
WorkItemAction = Literal[
    "assign",
    "acknowledge",
    "approve",
    "return",
    "complete",
    "dismiss",
]


class CompanyContextEntityRead(BaseSchema):
    id: uuid.UUID
    code: str | None = None
    name: str


class CompanyContextTaxRead(BaseSchema):
    scope: Literal["company", "branch"]
    configured: bool
    vat_registered: bool
    tax_id: str | None = None
    tax_branch_code: str | None = None
    price_vat_type: str
    vat_rate: float


class CompanyContextTransportRead(BaseSchema):
    authoritative_source: Literal["signed_token"] = "signed_token"
    company_header: str = "X-Company-ID"
    branch_header: str = "X-Branch-ID"
    client_context_is_trusted: bool = False
    switch_requires_new_token: bool = True


class CompanyContextRead(BaseSchema):
    contract_version: str = "2026-09-19.1"
    environment: RuntimeEnvironment
    company: CompanyContextEntityRead
    brand: CompanyContextEntityRead | None = None
    branch: CompanyContextEntityRead | None = None
    station_or_device_id: str | None = None
    business_type: str | None = None
    target_database: str | None = None
    timezone: str
    currency: str
    tax: CompanyContextTaxRead
    all_scope_allowed: dict[Literal["brand", "branch", "station"], bool]
    transport: CompanyContextTransportRead = Field(default_factory=CompanyContextTransportRead)
    updated_at: datetime


class EffectiveAccessRead(BaseSchema):
    contract_version: str = "2026-09-19.1"
    company_id: uuid.UUID
    user_id: uuid.UUID
    scope_types: list[str]
    assignment_ids: list[uuid.UUID]
    permissions: list[str]
    default_route: str
    modules: list[CompanyModuleAccessRead]


class CompanyWorkItemRead(BaseSchema):
    id: str
    type: str
    source_app: str
    severity: WorkItemSeverity
    title: str
    company_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    due_at: datetime | None = None
    status: WorkItemStatus
    permission_required: str
    available_actions: list[WorkItemAction]
    deep_link: str
    unread: bool
    business_impact: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime


class CompanyWorkItemListRead(BaseSchema):
    contract_version: str = "2026-09-19.1"
    items: list[CompanyWorkItemRead]
    total: int
    unread: int
    generated_at: datetime


class CompanyWorkItemActionRequest(BaseSchema):
    action: Literal["assign", "acknowledge", "dismiss"]
    owner_id: uuid.UUID | None = None
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return value.strip()


class CompanyOverviewMetricRead(BaseSchema):
    key: str
    label: str
    value: int | float | str
    severity: WorkItemSeverity = "info"
    deep_link: str | None = None


class CompanyOverviewSectionRead(BaseSchema):
    module_key: CompanyModuleKey
    title: str
    readiness: str
    data_source: str
    status: OperationalState
    metrics: list[CompanyOverviewMetricRead]
    updated_at: datetime
    stale: bool = False
    error_code: str | None = None


class CompanyOverviewRead(BaseSchema):
    contract_version: str = "2026-09-19.1"
    context: CompanyContextRead
    task_summary: dict[str, int]
    sections: list[CompanyOverviewSectionRead]
    generated_at: datetime


class OperationalComponentRead(BaseSchema):
    id: str
    component_type: Literal[
        "counter",
        "kitchen",
        "pickup",
        "printer",
        "cash_drawer",
        "payment",
        "legacy_sync",
        "reporting_sync",
        "webhook",
    ]
    name: str
    state: OperationalState
    company_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    station_key: str | None = None
    last_seen_at: datetime | None = None
    last_sync_at: datetime | None = None
    queue_size: int = 0
    error_code: str | None = None
    retryable: bool = False
    source_system: str
    updated_at: datetime


class OperationalStatusRead(BaseSchema):
    contract_version: str = "2026-09-19.1"
    components: list[OperationalComponentRead]
    summary: dict[OperationalState, int]
    generated_at: datetime


class CompanyErpReadinessAreaRead(BaseSchema):
    key: Literal["purchasing", "inventory", "finance_tax", "reporting"]
    title: str
    state: ErpReadinessState
    open_items: int = 0
    permission_required: str
    deep_link: str | None = None
    read_only: bool = True
    message: str


class CompanyErpExceptionRead(BaseSchema):
    id: str
    source: Literal["purchase", "transfer", "stock_count", "payable", "tax"]
    title: str
    reference: str
    severity: WorkItemSeverity
    branch_id: uuid.UUID | None = None
    branch_name: str | None = None
    owner_id: uuid.UUID | None = None
    age_hours: int = Field(ge=0)
    due_at: datetime | None = None
    deep_link: str
    permission_required: str
    evidence_reference: str
    created_at: datetime


class CompanyErpFinanceReadinessRead(BaseSchema):
    period_year: int
    period_month: int
    period_status: Literal["not_started", "open", "review", "closed", "locked"]
    tax_configured: bool
    open_blockers: int = 0
    open_warnings: int = 0
    pending_reconciliation: int = 0
    accountant_signoff: Literal["pending", "recorded"] = "pending"
    ready_to_close: bool = False
    deep_link: str | None = None


class CompanyErpControlRead(BaseSchema):
    key: str
    label: str
    state: Literal["enforced", "hold"]
    detail: str


class CompanyErpReadinessRead(BaseSchema):
    contract_version: str = "2026-09-22.1"
    context: CompanyContextRead
    areas: list[CompanyErpReadinessAreaRead]
    exceptions: list[CompanyErpExceptionRead]
    finance: CompanyErpFinanceReadinessRead | None = None
    controls: list[CompanyErpControlRead]
    summary: dict[str, int]
    source_system: Literal["operational_database"] = "operational_database"
    source_updated_at: datetime | None = None
    stale_after_seconds: int = 300
    generated_at: datetime


GovernanceState = Literal[
    "ready",
    "attention",
    "blocked",
    "hold",
    "disabled",
    "planned",
    "permission_denied",
]
GovernanceMode = Literal["read_only", "shadow", "disabled", "planned"]
ReleaseGateState = Literal["pass", "attention", "hold", "blocked", "planned"]
CoverageState = Literal["available", "read_only", "hold", "planned"]


class CompanyGovernanceMetricRead(BaseSchema):
    key: str
    label: str
    value: int | float | str
    severity: WorkItemSeverity = "info"


class CompanyGovernanceAreaRead(BaseSchema):
    key: str
    title: str
    state: GovernanceState
    mode: GovernanceMode
    source_system: str
    reason: str
    deep_link: str | None = None
    metrics: list[CompanyGovernanceMetricRead] = Field(default_factory=list)
    updated_at: datetime | None = None
    stale: bool = False


class CompanyReleaseGateRead(BaseSchema):
    key: str
    title: str
    state: ReleaseGateState
    server_enforced: bool = True
    reason: str
    evidence_reference: str | None = None


class CompanyCoverageAreaRead(BaseSchema):
    key: Literal[
        "platform",
        "company",
        "erp",
        "restaurant",
        "retail",
        "takeaway",
        "kitchen",
        "supply_chain",
        "public",
        "integration_reporting",
    ]
    title: str
    state: CoverageState
    entry_route: str
    release_boundary: str


class CompanyGovernanceRead(BaseSchema):
    contract_version: str = "2026-09-23.1"
    company_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    scope: Literal["company", "branch"]
    environment: RuntimeEnvironment
    release_commit: str
    production_authorized: Literal[False] = False
    areas: list[CompanyGovernanceAreaRead]
    release_gates: list[CompanyReleaseGateRead]
    coverage: list[CompanyCoverageAreaRead]
    summary: dict[str, int]
    stale_after_seconds: int = 300
    generated_at: datetime
