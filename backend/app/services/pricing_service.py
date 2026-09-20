from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.crm import Customer
from app.models.pricing import PriceCalculation
from app.models.product import PriceList, PriceListItem, Product, ProductVariant
from app.models.settings import BranchSettings
from app.schemas.pricing import (
    PricingCalculateRequest,
    PricingCalculationRead,
    PricingLineRead,
    PricingLineRequest,
)


CALCULATION_VERSION = "wp43.1"
QUOTE_TTL_SECONDS = 300
ROUNDING_RULE = "THB_HALF_UP_0.01"
TWOPLACES = Decimal("0.01")
FOURPLACES = Decimal("0.0001")


def q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def q4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def canonical_hash(value: Any) -> str:
    def default(item: Any) -> str:
        if isinstance(item, (datetime, uuid.UUID, Decimal)):
            return str(item)
        raise TypeError(f"Unsupported canonical value: {type(item).__name__}")

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def pricing_error(http_status: int, code: str, message: str, **context: Any) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message, **context},
    )


@dataclass(frozen=True)
class ResolvedPricingLine:
    product: Product
    variant: ProductVariant | None
    request: PricingLineRequest
    authoritative_unit_price: Decimal
    applied_unit_price: Decimal
    promotion_code: str | None
    promotion_discount_amount: Decimal
    line_discount_amount: Decimal
    order_discount_share: Decimal
    vat_type: str
    vat_rate: Decimal
    vat_amount: Decimal
    line_subtotal: Decimal
    line_total: Decimal
    price_source: str
    price_list_id: uuid.UUID | None
    price_list_version: int
    price_version: str
    effective_at: datetime
    discrepancy: bool
    override_requires_approval: bool
    override_deviation_pct: Decimal

    @property
    def override_requested(self) -> bool:
        return self.request.price_override is not None

    def read(self) -> PricingLineRead:
        return PricingLineRead(
            product_id=self.product.id,
            variant_id=self.variant.id if self.variant else None,
            product_name=self.product.name,
            sku=self.variant.sku if self.variant else self.product.sku,
            qty=q4(self.request.qty),
            authoritative_unit_price=self.authoritative_unit_price,
            applied_unit_price=self.applied_unit_price,
            promotion_code=self.promotion_code,
            promotion_discount_amount=self.promotion_discount_amount,
            line_discount_amount=self.line_discount_amount,
            order_discount_share=self.order_discount_share,
            vat_type=self.vat_type,
            vat_rate=self.vat_rate,
            vat_amount=self.vat_amount,
            line_subtotal=self.line_subtotal,
            line_total=self.line_total,
            price_source=self.price_source,
            price_list_id=self.price_list_id,
            price_list_version=self.price_list_version,
            price_version=self.price_version,
            effective_at=self.effective_at,
            rounding_rule=ROUNDING_RULE,
            discrepancy=self.discrepancy,
            override_requested=self.override_requested,
            override_requires_approval=self.override_requires_approval,
            override_deviation_pct=self.override_deviation_pct,
        )

    def snapshot(self) -> dict[str, Any]:
        return self.read().model_dump(mode="json")


@dataclass(frozen=True)
class PricingResult:
    request_hash: str
    calculation_hash: str
    calculation_version: str
    cart_version: int
    company_id: uuid.UUID
    brand_id: uuid.UUID | None
    branch_id: uuid.UUID
    channel: str
    currency: str
    customer_id: uuid.UUID | None
    price_list_id: uuid.UUID | None
    price_list_version: int
    subtotal: Decimal
    line_discount_amount: Decimal
    order_discount_amount: Decimal
    discount_amount: Decimal
    promotion_discount_amount: Decimal
    discount_percentage: Decimal
    vat_amount: Decimal
    total_amount: Decimal
    requires_price_override_approval: bool
    has_price_discrepancy: bool
    lines: tuple[ResolvedPricingLine, ...]

    def context(self) -> dict[str, Any]:
        return {
            "company_id": str(self.company_id),
            "brand_id": str(self.brand_id) if self.brand_id else None,
            "branch_id": str(self.branch_id),
            "channel": self.channel,
            "currency": self.currency,
            "customer_id": str(self.customer_id) if self.customer_id else None,
            "price_list_id": str(self.price_list_id) if self.price_list_id else None,
            "price_list_version": self.price_list_version,
            "calculation_version": self.calculation_version,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.context(),
            "request_hash": self.request_hash,
            "calculation_hash": self.calculation_hash,
            "cart_version": self.cart_version,
            "subtotal": str(self.subtotal),
            "line_discount_amount": str(self.line_discount_amount),
            "order_discount_amount": str(self.order_discount_amount),
            "discount_amount": str(self.discount_amount),
            "promotion_discount_amount": str(self.promotion_discount_amount),
            "discount_percentage": str(self.discount_percentage),
            "vat_amount": str(self.vat_amount),
            "total_amount": str(self.total_amount),
            "rounding_rule": ROUNDING_RULE,
            "lines": [line.snapshot() for line in self.lines],
        }


class PricingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        payload: PricingCalculateRequest,
        lock_prices: bool = False,
    ) -> PricingResult:
        branch_settings = await self.db.scalar(
            select(BranchSettings).where(
                BranchSettings.company_id == company_id,
                BranchSettings.branch_id == branch_id,
            )
        )
        if payload.customer_id is not None:
            customer_id = await self.db.scalar(
                select(Customer.id).where(
                    Customer.id == payload.customer_id,
                    Customer.company_id == company_id,
                    Customer.deleted_at.is_(None),
                )
            )
            if customer_id is None:
                raise pricing_error(
                    status.HTTP_409_CONFLICT,
                    "context_mismatch",
                    "Customer does not belong to the active Company",
                )
        price_list = await self._resolve_price_list(
            company_id=company_id,
            branch_id=branch_id,
            brand_id=brand_id,
            channel=payload.channel,
            currency=payload.currency,
            customer_id=payload.customer_id,
            preferred_id=branch_settings.pos_default_price_list_id if branch_settings else None,
            lock_prices=lock_prices,
        )
        request_value = payload.model_dump(mode="json", exclude={"idempotency_key"})
        request_hash = canonical_hash(
            {
                "company_id": str(company_id),
                "brand_id": str(brand_id) if brand_id else None,
                "branch_id": str(branch_id),
                **request_value,
            }
        )

        prepared: list[dict[str, Any]] = []
        gross_authoritative = Decimal("0")
        subtotal = Decimal("0")
        line_discount_total = Decimal("0")
        promotion_discount_total = Decimal("0")
        has_discrepancy = False
        requires_override_approval = False
        for line_request in payload.items:
            product, variant = await self._load_product(
                company_id,
                brand_id,
                line_request.product_id,
                line_request.variant_id,
                lock_prices=lock_prices,
            )
            authoritative_price, source, price_item = await self._resolve_item_price(
                company_id=company_id,
                product=product,
                variant=variant,
                qty=q4(line_request.qty),
                price_list=price_list,
                lock_prices=lock_prices,
            )
            if price_list is None and payload.currency != "THB":
                raise pricing_error(
                    status.HTTP_409_CONFLICT,
                    "context_mismatch",
                    "A matching price list is required for non-THB currency",
                    currency=payload.currency,
                )
            vat_type = str(product.vat_type).lower()
            vat_rate = q2(Decimal(product.vat_rate))
            if vat_type not in {"included", "excluded", "zero", "exempt"}:
                raise pricing_error(
                    status.HTTP_409_CONFLICT,
                    "tax_context_invalid",
                    "Product VAT type is not supported by this calculation contract",
                    product_id=str(product.id),
                    vat_type=product.vat_type,
                )
            if vat_rate < 0 or vat_rate > 100:
                raise pricing_error(
                    status.HTTP_409_CONFLICT,
                    "tax_context_invalid",
                    "Product VAT rate is outside the supported range",
                    product_id=str(product.id),
                    vat_rate=str(vat_rate),
                )
            base_catalog_price = q4(
                variant.selling_price
                if variant is not None and variant.selling_price is not None
                else product.selling_price
            )
            promotion_code = None
            promotion_discount = Decimal("0")
            if price_item is not None and price_list is not None and price_list.price_kind == "promotion":
                promotion_code = price_list.promotion_code or price_list.name
                promotion_discount = q4(
                    max(Decimal("0"), base_catalog_price - authoritative_price)
                    * q4(line_request.qty)
                )
            effective_at = self._price_effective_at(price_list, price_item, product, variant)
            list_version = int(price_list.version or 1) if price_list else 1
            price_version = canonical_hash(
                {
                    "calculation_version": CALCULATION_VERSION,
                    "product_id": str(product.id),
                    "product_updated_at": product.updated_at.isoformat() if product.updated_at else None,
                    "variant_id": str(variant.id) if variant else None,
                    "variant_updated_at": variant.updated_at.isoformat() if variant and variant.updated_at else None,
                    "price_list_id": str(price_list.id) if price_list else None,
                    "price_list_version": list_version,
                    "price_item_id": str(price_item.id) if price_item else None,
                    "authoritative_price": str(authoritative_price),
                    "vat_type": vat_type,
                    "vat_rate": str(vat_rate),
                    "promotion_code": promotion_code,
                    "effective_at": effective_at.isoformat(),
                }
            )
            if (
                line_request.expected_price_version is not None
                and line_request.expected_price_version != price_version
            ):
                raise pricing_error(
                    status.HTTP_409_CONFLICT,
                    "stale_price",
                    "Price version changed; refresh the cart before checkout",
                    product_id=str(product.id),
                    expected_price_version=line_request.expected_price_version,
                    current_price_version=price_version,
                )

            discrepancy = (
                line_request.expected_unit_price is not None
                and q4(line_request.expected_unit_price) != authoritative_price
            )
            has_discrepancy = has_discrepancy or discrepancy
            applied_price = authoritative_price
            deviation = Decimal("0")
            needs_approval = False
            if line_request.price_override is not None:
                applied_price = q4(line_request.price_override.requested_unit_price)
                deviation = self._override_deviation(authoritative_price, applied_price)
                needs_approval = self._validate_override_policy(
                    authoritative_price=authoritative_price,
                    applied_price=applied_price,
                    cost_price=Decimal(
                        variant.cost_price
                        if variant is not None and variant.cost_price is not None
                        else product.cost_price
                    ),
                    deviation_pct=deviation,
                    settings=branch_settings,
                )
                requires_override_approval = requires_override_approval or needs_approval

            unit_after_discount = self._apply_discount(
                applied_price,
                line_request.discount_amount,
                line_request.discount_type,
            )
            qty = q4(line_request.qty)
            line_subtotal = q4(unit_after_discount * qty)
            line_discount = q4((applied_price - unit_after_discount) * qty)
            gross_authoritative += q4(authoritative_price * qty)
            subtotal += line_subtotal
            line_discount_total += line_discount
            promotion_discount_total += promotion_discount
            prepared.append(
                {
                    "product": product,
                    "variant": variant,
                    "request": line_request,
                    "authoritative": authoritative_price,
                    "applied": applied_price,
                    "line_discount": line_discount,
                    "line_subtotal": line_subtotal,
                    "vat_type": vat_type,
                    "vat_rate": vat_rate,
                    "promotion_code": promotion_code,
                    "promotion_discount": promotion_discount,
                    "effective_at": effective_at,
                    "source": source,
                    "price_version": price_version,
                    "discrepancy": discrepancy,
                    "needs_approval": needs_approval,
                    "deviation": deviation,
                }
            )

        subtotal = q2(subtotal)
        order_discount = self._discount_value(subtotal, payload.discount_amount, payload.discount_type)
        if order_discount > subtotal:
            raise pricing_error(
                status.HTTP_400_BAD_REQUEST,
                "discount_exceeds_subtotal",
                "Order discount cannot exceed the authoritative subtotal",
                subtotal=str(subtotal),
                requested_discount=str(order_discount),
            )
        order_discount = q2(order_discount)
        remaining_discount = order_discount
        lines: list[ResolvedPricingLine] = []
        vat_total = Decimal("0")
        total_amount = Decimal("0")
        for index, row in enumerate(prepared):
            line_subtotal = q4(Decimal(row["line_subtotal"]))
            if index == len(prepared) - 1:
                share = q4(remaining_discount)
            elif subtotal > 0:
                share = q4(order_discount * line_subtotal / subtotal)
                remaining_discount -= share
            else:
                share = Decimal("0")
            taxable = q4(max(Decimal("0"), line_subtotal - share))
            vat_type = str(row["vat_type"])
            vat_rate = Decimal(row["vat_rate"])
            vat_amount = self._calculate_vat(taxable, vat_type, vat_rate)
            line_total = q4(taxable + (vat_amount if vat_type == "excluded" else Decimal("0")))
            vat_total += vat_amount
            total_amount += line_total
            lines.append(
                ResolvedPricingLine(
                    product=row["product"],
                    variant=row["variant"],
                    request=row["request"],
                    authoritative_unit_price=Decimal(row["authoritative"]),
                    applied_unit_price=Decimal(row["applied"]),
                    promotion_code=(str(row["promotion_code"]) if row["promotion_code"] else None),
                    promotion_discount_amount=Decimal(row["promotion_discount"]),
                    line_discount_amount=Decimal(row["line_discount"]),
                    order_discount_share=share,
                    vat_type=vat_type,
                    vat_rate=vat_rate,
                    vat_amount=vat_amount,
                    line_subtotal=line_subtotal,
                    line_total=line_total,
                    price_source=str(row["source"]),
                    price_list_id=price_list.id if price_list else None,
                    price_list_version=int(price_list.version or 1) if price_list else 1,
                    price_version=str(row["price_version"]),
                    effective_at=row["effective_at"],
                    discrepancy=bool(row["discrepancy"]),
                    override_requires_approval=bool(row["needs_approval"]),
                    override_deviation_pct=Decimal(row["deviation"]),
                )
            )

        total_discount = q2(line_discount_total + order_discount)
        discount_percentage = (
            q2(total_discount * Decimal("100") / gross_authoritative)
            if gross_authoritative > 0
            else Decimal("0")
        )
        calculation_payload = {
            "request_hash": request_hash,
            "calculation_version": CALCULATION_VERSION,
            "company_id": str(company_id),
            "brand_id": str(brand_id) if brand_id else None,
            "branch_id": str(branch_id),
            "channel": payload.channel,
            "currency": payload.currency,
            "price_list_id": str(price_list.id) if price_list else None,
            "price_list_version": int(price_list.version or 1) if price_list else 1,
            "subtotal": str(subtotal),
            "discount_amount": str(total_discount),
            "promotion_discount_amount": str(q2(promotion_discount_total)),
            "vat_amount": str(q2(vat_total)),
            "total_amount": str(q2(total_amount)),
            "lines": [line.snapshot() for line in lines],
        }
        calculation_hash = canonical_hash(calculation_payload)
        return PricingResult(
            request_hash=request_hash,
            calculation_hash=calculation_hash,
            calculation_version=CALCULATION_VERSION,
            cart_version=payload.cart_version,
            company_id=company_id,
            brand_id=brand_id,
            branch_id=branch_id,
            channel=payload.channel,
            currency=payload.currency,
            customer_id=payload.customer_id,
            price_list_id=price_list.id if price_list else None,
            price_list_version=int(price_list.version or 1) if price_list else 1,
            subtotal=subtotal,
            line_discount_amount=q2(line_discount_total),
            order_discount_amount=order_discount,
            discount_amount=total_discount,
            promotion_discount_amount=q2(promotion_discount_total),
            discount_percentage=discount_percentage,
            vat_amount=q2(vat_total),
            total_amount=q2(total_amount),
            requires_price_override_approval=requires_override_approval,
            has_price_discrepancy=has_discrepancy,
            lines=tuple(lines),
        )

    async def create_quote(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        user_id: uuid.UUID,
        payload: PricingCalculateRequest,
    ) -> PricingCalculationRead:
        request_hash = canonical_hash(
            {
                "company_id": str(company_id),
                "brand_id": str(brand_id) if brand_id else None,
                "branch_id": str(branch_id),
                **payload.model_dump(mode="json", exclude={"idempotency_key"}),
            }
        )
        existing = await self.db.scalar(
            select(PriceCalculation).where(
                PriceCalculation.company_id == company_id,
                PriceCalculation.branch_id == branch_id,
                PriceCalculation.operation == "calculate",
                PriceCalculation.idempotency_key == payload.idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise pricing_error(
                    status.HTTP_409_CONFLICT,
                    "duplicate_request",
                    "Idempotency key was already used with a different pricing request",
                    idempotency_key=payload.idempotency_key,
                )
            return PricingCalculationRead.model_validate(existing.result_json)

        result = await self.calculate(
            company_id=company_id,
            branch_id=branch_id,
            brand_id=brand_id,
            payload=payload,
        )
        quote_id = uuid.uuid4()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=QUOTE_TTL_SECONDS)
        read = self._result_read(result, quote_id, payload.idempotency_key, expires_at)
        self.db.add(
            PriceCalculation(
                id=quote_id,
                company_id=company_id,
                brand_id=brand_id,
                branch_id=branch_id,
                user_id=user_id,
                customer_id=payload.customer_id,
                operation="calculate",
                channel=payload.channel,
                currency=payload.currency,
                idempotency_key=payload.idempotency_key,
                request_hash=result.request_hash,
                calculation_hash=result.calculation_hash,
                calculation_version=result.calculation_version,
                cart_version=result.cart_version,
                price_list_id=result.price_list_id,
                price_list_version=result.price_list_version,
                context_json=result.context(),
                result_json=read.model_dump(mode="json"),
                expires_at=expires_at,
            )
        )
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            replay = await self.db.scalar(
                select(PriceCalculation).where(
                    PriceCalculation.company_id == company_id,
                    PriceCalculation.branch_id == branch_id,
                    PriceCalculation.operation == "calculate",
                    PriceCalculation.idempotency_key == payload.idempotency_key,
                )
            )
            if replay is not None and replay.request_hash == request_hash:
                return PricingCalculationRead.model_validate(replay.result_json)
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "duplicate_request",
                "Pricing request conflicted with an existing idempotency key",
                idempotency_key=payload.idempotency_key,
            ) from exc
        return read

    async def validate_quote(
        self,
        *,
        quote_id: uuid.UUID,
        calculation_hash: str,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        user_id: uuid.UUID,
        current_result: PricingResult,
    ) -> PriceCalculation:
        quote = await self.db.scalar(
            select(PriceCalculation)
            .where(
                PriceCalculation.id == quote_id,
                PriceCalculation.company_id == company_id,
                PriceCalculation.branch_id == branch_id,
            )
            .with_for_update()
        )
        if quote is None:
            raise pricing_error(status.HTTP_404_NOT_FOUND, "pricing_quote_not_found", "Pricing quote was not found")
        if quote.user_id != user_id:
            raise pricing_error(status.HTTP_409_CONFLICT, "context_mismatch", "Pricing quote belongs to another user context")
        if quote.expires_at <= datetime.now(timezone.utc):
            raise pricing_error(status.HTTP_409_CONFLICT, "stale_price", "Pricing quote expired; recalculate before checkout")
        if quote.status == "consumed":
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "duplicate_request",
                "Pricing quote has already been consumed",
                consumed_order_id=str(quote.consumed_order_id) if quote.consumed_order_id else None,
            )
        if current_result.cart_version != quote.cart_version:
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "version_conflict",
                "Cart version changed after pricing; recalculate before checkout",
                quoted_cart_version=quote.cart_version,
                current_cart_version=current_result.cart_version,
            )
        quoted_context = quote.context_json or {}
        current_context = current_result.context()
        context_fields = ("company_id", "brand_id", "branch_id", "channel", "currency", "customer_id")
        if any(quoted_context.get(field) != current_context.get(field) for field in context_fields):
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "context_mismatch",
                "Company, Brand, Branch, Channel, Customer or currency changed after pricing",
            )
        if calculation_hash != quote.calculation_hash:
            raise pricing_error(status.HTTP_409_CONFLICT, "context_mismatch", "Pricing quote hash does not match")
        if current_result.calculation_hash != quote.calculation_hash:
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "stale_price",
                "Price, tax, discount or context changed; recalculate before checkout",
                quote_calculation_hash=quote.calculation_hash,
                current_calculation_hash=current_result.calculation_hash,
            )
        return quote

    @staticmethod
    def consume_quote(quote: PriceCalculation, order_id: uuid.UUID) -> None:
        quote.status = "consumed"
        quote.consumed_order_id = order_id
        quote.consumed_at = datetime.now(timezone.utc)

    @staticmethod
    def _result_read(
        result: PricingResult,
        quote_id: uuid.UUID,
        idempotency_key: str,
        expires_at: datetime,
    ) -> PricingCalculationRead:
        return PricingCalculationRead(
            quote_id=quote_id,
            idempotency_key=idempotency_key,
            request_hash=result.request_hash,
            calculation_hash=result.calculation_hash,
            calculation_version=result.calculation_version,
            cart_version=result.cart_version,
            company_id=result.company_id,
            brand_id=result.brand_id,
            branch_id=result.branch_id,
            channel=result.channel,
            currency=result.currency,
            price_list_id=result.price_list_id,
            price_list_version=result.price_list_version,
            subtotal=result.subtotal,
            line_discount_amount=result.line_discount_amount,
            order_discount_amount=result.order_discount_amount,
            discount_amount=result.discount_amount,
            promotion_discount_amount=result.promotion_discount_amount,
            discount_percentage=result.discount_percentage,
            vat_amount=result.vat_amount,
            total_amount=result.total_amount,
            rounding_rule=ROUNDING_RULE,
            effective_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            requires_price_override_approval=result.requires_price_override_approval,
            has_price_discrepancy=result.has_price_discrepancy,
            lines=[line.read() for line in result.lines],
        )

    async def _resolve_price_list(
        self,
        *,
        company_id: uuid.UUID,
        branch_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        channel: str,
        currency: str,
        customer_id: uuid.UUID | None,
        preferred_id: uuid.UUID | None,
        lock_prices: bool,
    ) -> PriceList | None:
        now = datetime.now(timezone.utc)
        today = now.date()
        statement = select(PriceList).where(
            PriceList.company_id == company_id,
            PriceList.deleted_at.is_(None),
            PriceList.is_active.is_(True),
            PriceList.currency == currency,
            or_(PriceList.valid_from.is_(None), PriceList.valid_from <= today),
            or_(PriceList.valid_until.is_(None), PriceList.valid_until >= today),
            or_(PriceList.valid_from_at.is_(None), PriceList.valid_from_at <= now),
            or_(PriceList.valid_until_at.is_(None), PriceList.valid_until_at >= now),
            or_(PriceList.branch_id.is_(None), PriceList.branch_id == branch_id),
            or_(PriceList.brand_id.is_(None), PriceList.brand_id == brand_id),
            or_(PriceList.channel.is_(None), PriceList.channel == channel),
            or_(PriceList.customer_id.is_(None), PriceList.customer_id == customer_id),
        )
        if lock_prices:
            statement = statement.with_for_update()
        rows = list((await self.db.scalars(statement)).all())
        if not rows:
            return None

        def score(row: PriceList) -> tuple[int, int, int, str]:
            specificity = sum(
                int(value is not None)
                for value in (row.customer_id, row.branch_id, row.brand_id, row.channel)
            )
            preferred = int(preferred_id is not None and row.id == preferred_id)
            return specificity, preferred, int(row.priority or 0), str(row.id)

        return max(rows, key=score)

    async def _load_product(
        self,
        company_id: uuid.UUID,
        brand_id: uuid.UUID | None,
        product_id: uuid.UUID,
        variant_id: uuid.UUID | None,
        *,
        lock_prices: bool,
    ) -> tuple[Product, ProductVariant | None]:
        statement = (
            select(Product)
            .where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted_at.is_(None),
                Product.is_active.is_(True),
                Product.is_for_sale.is_(True),
            )
            .options(selectinload(Product.unit))
        )
        if lock_prices:
            statement = statement.with_for_update()
        product = await self.db.scalar(statement)
        if product is None:
            raise pricing_error(status.HTTP_404_NOT_FOUND, "product_not_sellable", "Product is unavailable", product_id=str(product_id))
        if brand_id is not None and product.brand_id is not None and product.brand_id != brand_id:
            raise pricing_error(status.HTTP_409_CONFLICT, "context_mismatch", "Product does not belong to the active Brand", product_id=str(product_id))
        variant = None
        if variant_id is not None:
            variant_statement = select(ProductVariant).where(
                ProductVariant.id == variant_id,
                ProductVariant.product_id == product.id,
                ProductVariant.company_id == company_id,
                ProductVariant.deleted_at.is_(None),
                ProductVariant.is_active.is_(True),
            )
            if lock_prices:
                variant_statement = variant_statement.with_for_update()
            variant = await self.db.scalar(variant_statement)
            if variant is None:
                raise pricing_error(status.HTTP_404_NOT_FOUND, "variant_not_sellable", "Product variant is unavailable", variant_id=str(variant_id))
        return product, variant

    async def _resolve_item_price(
        self,
        *,
        company_id: uuid.UUID,
        product: Product,
        variant: ProductVariant | None,
        qty: Decimal,
        price_list: PriceList | None,
        lock_prices: bool,
    ) -> tuple[Decimal, str, PriceListItem | None]:
        price_item = None
        if price_list is not None:
            statement = (
                select(PriceListItem)
                .where(
                    PriceListItem.company_id == company_id,
                    PriceListItem.price_list_id == price_list.id,
                    PriceListItem.product_id == product.id,
                    PriceListItem.min_qty <= qty,
                )
                .order_by(PriceListItem.min_qty.desc())
            )
            statement = (
                statement.where(PriceListItem.variant_id == variant.id)
                if variant is not None
                else statement.where(PriceListItem.variant_id.is_(None))
            )
            if lock_prices:
                statement = statement.with_for_update()
            price_item = await self.db.scalar(statement)
        if price_item is not None:
            return q4(price_item.price), "price_list", price_item
        if variant is not None and variant.selling_price is not None:
            return q4(variant.selling_price), "variant", None
        return q4(product.selling_price), "product", None

    @staticmethod
    def _price_effective_at(
        price_list: PriceList | None,
        price_item: PriceListItem | None,
        product: Product,
        variant: ProductVariant | None,
    ) -> datetime:
        if price_list is not None and price_list.valid_from_at is not None:
            return price_list.valid_from_at
        if price_list is not None and price_list.valid_from is not None:
            return datetime.combine(price_list.valid_from, datetime.min.time(), tzinfo=timezone.utc)
        for candidate in (
            price_item.updated_at if price_item is not None else None,
            variant.updated_at if variant is not None else None,
            product.updated_at,
        ):
            if candidate is not None:
                return candidate if candidate.tzinfo is not None else candidate.replace(tzinfo=timezone.utc)
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    @staticmethod
    def _apply_discount(base: Decimal, amount: Decimal, kind: str) -> Decimal:
        value = Decimal(amount)
        if kind == "percent":
            if value > 100:
                raise pricing_error(status.HTTP_400_BAD_REQUEST, "invalid_discount", "Discount percent cannot exceed 100")
            discount = base * value / Decimal("100")
        else:
            discount = value
        if discount > base:
            raise pricing_error(status.HTTP_400_BAD_REQUEST, "invalid_discount", "Line discount cannot exceed unit price")
        return q4(base - discount)

    @staticmethod
    def _discount_value(base: Decimal, amount: Decimal, kind: str) -> Decimal:
        value = Decimal(amount)
        if kind == "percent":
            if value > 100:
                raise pricing_error(status.HTTP_400_BAD_REQUEST, "invalid_discount", "Discount percent cannot exceed 100")
            return q2(base * value / Decimal("100"))
        return q2(value)

    @staticmethod
    def _calculate_vat(amount: Decimal, vat_type: str, vat_rate: Decimal) -> Decimal:
        if vat_type == "included" and vat_rate > 0:
            return q4(amount * vat_rate / (Decimal("100") + vat_rate))
        if vat_type == "excluded" and vat_rate > 0:
            return q4(amount * vat_rate / Decimal("100"))
        return Decimal("0.0000")

    @staticmethod
    def _override_deviation(authoritative: Decimal, applied: Decimal) -> Decimal:
        if authoritative <= 0:
            return Decimal("0") if applied == authoritative else Decimal("100")
        return q4(abs(applied - authoritative) * Decimal("100") / authoritative)

    @staticmethod
    def _validate_override_policy(
        *,
        authoritative_price: Decimal,
        applied_price: Decimal,
        cost_price: Decimal,
        deviation_pct: Decimal,
        settings: BranchSettings | None,
    ) -> bool:
        auto_limit = Decimal(
            settings.pos_price_override_auto_limit_pct
            if settings is not None and settings.pos_price_override_auto_limit_pct is not None
            else 10
        )
        auto_amount = Decimal(
            settings.pos_price_override_auto_limit_amount
            if settings is not None and settings.pos_price_override_auto_limit_amount is not None
            else 100
        )
        max_deviation = Decimal(
            settings.pos_price_override_max_deviation_pct
            if settings is not None and settings.pos_price_override_max_deviation_pct is not None
            else 50
        )
        min_margin = Decimal(
            settings.pos_price_override_min_margin_pct
            if settings is not None and settings.pos_price_override_min_margin_pct is not None
            else 0
        )
        if deviation_pct > max_deviation:
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "price_override_limit_exceeded",
                "Requested price exceeds the Branch override limit",
                deviation_percentage=str(deviation_pct),
                maximum_percentage=str(max_deviation),
            )
        margin = (
            q4((applied_price - cost_price) * Decimal("100") / applied_price)
            if applied_price > 0
            else Decimal("-100")
        )
        if margin < min_margin:
            raise pricing_error(
                status.HTTP_409_CONFLICT,
                "price_override_margin_violation",
                "Requested price is below the minimum margin policy",
                margin_percentage=str(margin),
                minimum_margin_percentage=str(min_margin),
            )
        return deviation_pct > auto_limit or abs(applied_price - authoritative_price) > auto_amount
