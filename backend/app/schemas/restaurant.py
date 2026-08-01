from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import ConfigDict, Field

from app.schemas import BaseSchema


# ── Recipe Ingredient ────────────────────────────────────────────────────────

class RecipeIngredientBase(BaseSchema):
    ingredient_id: uuid.UUID
    quantity: Decimal
    unit: str
    sort_order: int = 0
    notes: str | None = None


class RecipeIngredientCreate(RecipeIngredientBase):
    pass


class RecipeIngredientRead(RecipeIngredientBase):
    id: uuid.UUID
    recipe_id: uuid.UUID
    ingredient_name: str = ""
    ingredient_sku: str = ""
    image_url: str | None = None
    latest_unit_cost: Decimal = Decimal("0")
    cost_per_recipe: Decimal = Decimal("0")

    model_config = ConfigDict(from_attributes=True)


# ── Recipe ───────────────────────────────────────────────────────────────────

class RecipeCreate(BaseSchema):
    product_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    selling_price: Decimal | None = None
    recipe_type: str = "menu_recipe"
    version_no: int = 1
    effective_from: date | None = None
    effective_to: date | None = None
    name: str
    yield_qty: Decimal = Decimal("1")
    yield_unit: str = "แก้ว"
    loss_percent: Decimal = Decimal("0")
    notes: str | None = None
    ingredients: list[RecipeIngredientCreate] = []


class RecipeUpdate(BaseSchema):
    name: str | None = None
    selling_price: Decimal | None = None
    recipe_type: str | None = None
    version_no: int | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    yield_qty: Decimal | None = None
    yield_unit: str | None = None
    loss_percent: Decimal | None = None
    notes: str | None = None
    is_active: bool | None = None
    ingredients: list[RecipeIngredientCreate] | None = None


class RecipeInventoryUpdate(BaseSchema):
    product_id: uuid.UUID
    product_name: str
    inventory_role: Literal["central_raw", "central_ready", "store_local"]
    location_id: uuid.UUID
    location_name: str
    role_assigned: bool = False
    balance_created: bool = False


class CentralProductionStockItem(BaseSchema):
    product_id: uuid.UUID
    qty: Decimal
    cost_per_unit: Decimal | None = None


class CentralProductionCompleteRequest(BaseSchema):
    location_id: uuid.UUID
    date_from: date | None = None
    date_to: date | None = None
    status: str | None = None
    outputs: list[CentralProductionStockItem] = []
    inputs: list[CentralProductionStockItem] = []
    note: str | None = None


class ProductionBatchLineCreate(BaseSchema):
    product_id: uuid.UUID
    planned_qty: Decimal
    unit_code: str | None = None
    cost_per_unit: Decimal | None = None


class ProductionBatchCreate(BaseSchema):
    planned_date: date
    inputs: list[ProductionBatchLineCreate] = Field(default_factory=list)
    outputs: list[ProductionBatchLineCreate] = Field(default_factory=list)
    note: str | None = None


class ProductionBatchActualLine(BaseSchema):
    line_id: uuid.UUID
    actual_qty: Decimal


class ProductionBatchCompleteRequest(BaseSchema):
    lines: list[ProductionBatchActualLine] = Field(default_factory=list)
    note: str | None = None


class ProductionBatchLineRead(BaseSchema):
    id: uuid.UUID
    line_type: Literal["input", "output"]
    product_id: uuid.UUID
    product_name: str
    product_sku: str
    source_location_id: uuid.UUID | None = None
    source_location_name: str | None = None
    destination_location_id: uuid.UUID | None = None
    destination_location_name: str | None = None
    planned_qty: Decimal
    actual_qty: Decimal | None = None
    unit_code: str
    cost_per_unit: Decimal
    sort_order: int


class ProductionBatchRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    brand_id: uuid.UUID
    batch_number: str
    planned_date: date
    status: Literal["draft", "planned", "in_progress", "completed", "cancelled"]
    raw_location_id: uuid.UUID
    raw_location_name: str
    ready_location_id: uuid.UUID
    ready_location_name: str
    planned_by: uuid.UUID
    started_by: uuid.UUID | None = None
    completed_by: uuid.UUID | None = None
    planned_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    note: str | None = None
    lines: list[ProductionBatchLineRead] = Field(default_factory=list)


class RecipeRead(BaseSchema):
    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID | None
    brand_id: uuid.UUID | None = None
    product_id: uuid.UUID
    product_name: str = ""
    product_sku: str = ""
    recipe_type: str
    version_no: int
    effective_from: date | None = None
    effective_to: date | None = None
    name: str
    yield_qty: Decimal
    yield_unit: str
    loss_percent: Decimal
    effective_yield_qty: Decimal = Decimal("1")
    notes: str | None
    is_active: bool
    ingredients: list[RecipeIngredientRead] = []
    total_cost: Decimal = Decimal("0")
    cost_per_yield: Decimal = Decimal("0")
    selling_price: Decimal = Decimal("0")
    gross_margin_pct: Decimal = Decimal("0")
    inventory_updates: list[RecipeInventoryUpdate] = []

    model_config = ConfigDict(from_attributes=True)


class RecipeListItem(BaseSchema):
    id: uuid.UUID
    product_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    product_name: str = ""
    name: str
    recipe_type: str
    version_no: int
    yield_unit: str
    is_active: bool
    total_cost: Decimal = Decimal("0")
    cost_per_yield: Decimal = Decimal("0")
    selling_price: Decimal = Decimal("0")
    gross_margin_pct: Decimal = Decimal("0")

    model_config = ConfigDict(from_attributes=True)


# ── Raw Material ──────────────────────────────────────────────────────────────

class RawMaterialCreate(BaseSchema):
    sku: str
    name: str
    cost_price: Decimal = Decimal("0")
    unit: str = "g"
    inventory_role: Literal["central_raw", "central_ready", "store_local"] = "central_raw"


# ── Dining Table ─────────────────────────────────────────────────────────────

class TableCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=100)
    zone: str = Field(default="โซนทั่วไป", min_length=1, max_length=100)
    capacity: int = Field(default=4, ge=1, le=100)
    table_type: str = "dine_in"
    sort_order: int = 0


class TableUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    zone: str | None = Field(default=None, min_length=1, max_length=100)
    capacity: int | None = Field(default=None, ge=1, le=100)
    status: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class TableRead(BaseSchema):
    id: uuid.UUID
    branch_id: uuid.UUID
    name: str
    zone: str
    capacity: int
    session_qr_token: uuid.UUID | None = None
    table_type: str
    status: str
    sort_order: int
    is_active: bool
    active_session_id: uuid.UUID | None = None
    queue_number: int | None = None
    pending_count: int = 0
    cooking_count: int = 0
    ready_count: int = 0
    served_count: int = 0
    qr_pending_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# ── Unified F&B Setup ───────────────────────────────────────────────────────

class FBTableZoneSetup(BaseSchema):
    zone_name: str = Field(min_length=1, max_length=100)
    table_count: int = Field(ge=1, le=100)
    table_name_prefix: str = Field(min_length=1, max_length=40)
    table_capacity: int = Field(ge=1, le=100)


class FBSetupRequest(BaseSchema):
    has_tables: bool
    table_zones: list[FBTableZoneSetup] = Field(default_factory=list, max_length=20)
    # Legacy fields remain available for cached clients during a rolling deploy.
    table_count: int = Field(default=0, ge=0, le=100)
    table_name_prefix: str = Field(default="โต๊ะ", min_length=1, max_length=40)
    table_capacity: int = Field(default=4, ge=1, le=100)
    table_qr_enabled: bool = True
    bill_at_table: bool = True
    queue_reset: Literal["daily", "per_shift"] = "daily"
    queue_prefix: str = Field(default="", max_length=10)
    pickup_display_enabled: bool = True
    kitchen_stations: list[str] = Field(default_factory=list, max_length=30)


class FBSettingsUpdate(BaseSchema):
    has_tables: bool | None = None
    table_qr_enabled: bool | None = None
    bill_at_table: bool | None = None
    queue_reset: Literal["daily", "per_shift"] | None = None
    queue_prefix: str | None = Field(default=None, max_length=10)
    pickup_display_enabled: bool | None = None
    line_notify_token: str | None = Field(default=None, max_length=255)
    kitchen_stations: list[str] | None = Field(default=None, max_length=30)


# ── Dining Session ────────────────────────────────────────────────────────────

class SessionOpen(BaseSchema):
    table_id: uuid.UUID | None = None
    guest_count: int = 1
    customer_name: str | None = None
    customer_phone: str | None = None


class SessionRead(BaseSchema):
    id: uuid.UUID
    branch_id: uuid.UUID
    table_id: uuid.UUID | None
    qr_token: uuid.UUID
    table_name: str | None = None
    queue_number: int | None
    status: str
    guest_count: int
    customer_name: str | None
    customer_phone: str | None
    opened_at: str
    orders: list["DiningOrderRead"] = []

    model_config = ConfigDict(from_attributes=True)


# ── Dining Order ──────────────────────────────────────────────────────────────

class OrderItemCreate(BaseSchema):
    product_id: uuid.UUID
    qty: int = Field(default=1, ge=1, le=99)
    special_request: str | None = Field(default=None, max_length=500)


class PlaceOrderRequest(BaseSchema):
    items: list[OrderItemCreate] = Field(min_length=1, max_length=50)
    note: str | None = Field(default=None, max_length=1000)


class CancelRequest(BaseSchema):
    reason: str


class DiningOrderItemRead(BaseSchema):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    qty: int
    unit_price: Decimal
    special_request: str | None
    status: str

    model_config = ConfigDict(from_attributes=True)


class DiningOrderRead(BaseSchema):
    id: uuid.UUID
    session_id: uuid.UUID
    order_number: str
    source: str
    status: str
    items: list[DiningOrderItemRead] = []

    model_config = ConfigDict(from_attributes=True)


# ── Kitchen Ticket ────────────────────────────────────────────────────────────

class KitchenTicketRead(BaseSchema):
    id: uuid.UUID
    session_id: uuid.UUID
    order_item_id: uuid.UUID
    product_name: str
    qty: int
    special_request: str | None
    station: str | None
    queue_number: int | None
    table_name: str | None
    status: str
    created_at: str
    done_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class TicketStatusUpdate(BaseSchema):
    status: str


# ── Session Checkout ──────────────────────────────────────────────────────────

class SessionCheckoutRequest(BaseSchema):
    shift_id: uuid.UUID | None = None      # None = auto-detect จาก open shift
    location_id: uuid.UUID | None = None   # None = auto-detect จาก shift
    payment_method: str
    paid_amount: Decimal
    payments: list[dict] = []          # [{payment_method, amount, reference_no}]
    discount_amount: Decimal = Decimal("0")
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_tax_id: str | None = None
    customer_id: uuid.UUID | None = None
    note: str | None = None
    approval_token: str | None = None


class SessionCheckoutResult(BaseSchema):
    sale_order_id: uuid.UUID
    order_number: str
    total_amount: Decimal
    paid_amount: Decimal
    change_amount: Decimal
    session_id: uuid.UUID
    table_name: str | None = None
    queue_number: int | None = None
    source_type: str = "dine_in"
    customer_name: str | None = None
    customer_phone: str | None = None
    payment_method: str
    note: str | None = None


# ── Staff WAP Quick Service ──────────────────────────────────────────────────

class WapPaymentCreate(BaseSchema):
    payment_method: str
    amount: Decimal
    reference_no: str | None = None


class WapPaidOrderRequest(BaseSchema):
    items: list[OrderItemCreate]
    payment_method: str
    paid_amount: Decimal
    payments: list[WapPaymentCreate] = Field(default_factory=list)
    shift_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    customer_tax_id: str | None = None
    note: str | None = None
    client_order_id: str | None = Field(default=None, min_length=1, max_length=100)
    local_created_at: datetime | None = None
    local_customer_slip_printed_at: datetime | None = None
    local_kitchen_slip_printed_at: datetime | None = None
    is_offline: bool = False


class WapOfflinePaidOrderRequest(WapPaidOrderRequest):
    client_order_id: str = Field(min_length=1, max_length=100)
    is_offline: bool = True


class WapOfflineSyncRequest(BaseSchema):
    orders: list[WapOfflinePaidOrderRequest] = Field(min_length=1, max_length=50)


class WapOrderItemRead(BaseSchema):
    product_id: uuid.UUID
    product_name: str
    qty: int
    unit_price: Decimal
    special_request: str | None = None


class WapOrderRead(BaseSchema):
    session_id: uuid.UUID
    order_id: uuid.UUID
    sale_order_id: uuid.UUID
    sale_order_number: str
    opened_by: uuid.UUID | None = None
    cashier_user_id: uuid.UUID | None = None
    queue_number: int | None
    queue_display: str | None = None
    status: str
    customer_name: str | None = None
    customer_phone: str | None = None
    subtotal: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    change_amount: Decimal
    payment_method: str
    customer_slip_printed_at: str | None = None
    kitchen_slip_printed_at: str | None = None
    kitchen_sent_at: str | None = None
    recipe_stock_status: str | None = None
    recipe_stock_warnings: list[str] = Field(default_factory=list)
    created_at: str | None = None
    client_order_id: str | None = None
    items: list[WapOrderItemRead] = Field(default_factory=list)


class WapOfflineSyncItemRead(BaseSchema):
    client_order_id: str
    status: Literal["synced", "needs_review"]
    order: WapOrderRead | None = None
    error: str | None = None


class WapOfflineSyncRead(BaseSchema):
    results: list[WapOfflineSyncItemRead] = Field(default_factory=list)


class StoreStockAdjustmentRequest(BaseSchema):
    product_id: uuid.UUID
    qty: Decimal
    kind: Literal["waste", "adjustment"]
    reason: Literal[
        "prep_waste",
        "expired",
        "staff_sample",
        "return_central",
        "count_higher",
        "count_lower",
        "other",
    ]
    note: str | None = None


class ReplenishmentPolicyUpdateRequest(BaseSchema):
    is_enabled: bool = True
    safety_stock_percent: Decimal = Field(default=Decimal("10"), ge=0, le=1000)
    safety_stock_qty: Decimal = Field(default=Decimal("0"), ge=0)
    pack_size: Decimal = Field(default=Decimal("1"), gt=0)
    lead_time_days: int = Field(default=1, ge=1, le=365)
    forecast_method: Literal["auto", "latest_day", "average_7_open_days"] = "auto"
    minimum_order_qty: Decimal = Field(default=Decimal("0"), ge=0)


class StockCutoverExecuteRequest(BaseSchema):
    preview_token: str = Field(min_length=64, max_length=64)
    confirmation_text: str
    note: str | None = None


class CentralOrderSubmitItem(BaseSchema):
    product_id: uuid.UUID | None = None
    sku: str
    product_name: str
    unit: str = "ชิ้น"
    system_qty: Decimal
    requested_qty: Decimal
    source: str | None = None


class CentralOrderSubmitRequest(BaseSchema):
    items: list[CentralOrderSubmitItem]
    note: str | None = None


class CentralOrderQtyUpdateItem(BaseSchema):
    item_id: uuid.UUID
    qty: Decimal


class CentralOrderQtyUpdateRequest(BaseSchema):
    items: list[CentralOrderQtyUpdateItem] = []


class CentralOrderReceiveItem(BaseSchema):
    item_id: uuid.UUID
    qty_received: Decimal


class CentralOrderReceiveRequest(BaseSchema):
    items: list[CentralOrderReceiveItem] = []
    finalize: bool = True
    note: str | None = None


class CreditTopupRequest(BaseSchema):
    branch_id: uuid.UUID
    amount: Decimal
    note: str | None = None


class CreditAdjustmentRequest(BaseSchema):
    branch_id: uuid.UUID
    amount: Decimal
    note: str | None = None


class CreditTopupReviewRequest(BaseSchema):
    note: str | None = None


class BrandBranchTypeUpdateRequest(BaseSchema):
    branch_type: str


class BrandTransferConfigUpdateRequest(BaseSchema):
    central_branch_id: uuid.UUID | None = None
    central_location_id: uuid.UUID | None = None
    central_ready_location_id: uuid.UUID | None = None
    store_location_id: uuid.UUID | None = None


class BrandCreateRequest(BaseSchema):
    slug: str
    name: str
    business_type: Literal["restaurant"] = "restaurant"
    storefront_mode: str = "food_stall"
    theme_config: dict | None = None
    is_active: bool = True


class BrandUpdateRequest(BaseSchema):
    slug: str | None = None
    name: str | None = None
    storefront_mode: str | None = None
    theme_config: dict | None = None
    is_active: bool | None = None


class BrandBranchUpdateRequest(BaseSchema):
    branch_id: uuid.UUID
    branch_type: str = "company_owned"
    is_active: bool = True


# ── Public Menu (QR) ──────────────────────────────────────────────────────────

class PublicMenuProduct(BaseSchema):
    id: uuid.UUID
    name: str
    description: str | None
    selling_price: Decimal
    category_id: uuid.UUID | None
    category_name: str | None = None
    image_url: str | None
    is_available: bool


class PublicMenuResponse(BaseSchema):
    session_id: uuid.UUID
    queue_number: int | None
    table_name: str | None
    source_type: str = "dine_in"
    branch_name: str
    fb_service_mode: str
    categories: list[dict]
    products: list[PublicMenuProduct]
    session_status: str
    opened_at: str
    bill_at_table_enabled: bool = False


class PublicOrderHistory(BaseSchema):
    id: uuid.UUID
    order_number: str
    status: str
    note: str | None
    created_at: str
    subtotal: Decimal
    items: list[DiningOrderItemRead]


class PublicOrderStatus(BaseSchema):
    session_id: uuid.UUID
    queue_number: int | None
    session_status: str
    items: list[DiningOrderItemRead]
    orders: list[PublicOrderHistory]
    total_item_count: int
    total_amount: Decimal


# ── Ingredient Usage Report ───────────────────────────────────────────────────

class IngredientUsageItem(BaseSchema):
    ingredient_id: uuid.UUID
    ingredient_name: str
    ingredient_sku: str
    theoretical_qty: Decimal
    unit: str
    latest_unit_cost: Decimal
    total_cost: Decimal


class IngredientUsageReport(BaseSchema):
    branch_id: uuid.UUID
    date_from: str
    date_to: str
    items: list[IngredientUsageItem]
    grand_total_cost: Decimal


SessionRead.model_rebuild()
