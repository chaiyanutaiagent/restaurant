from __future__ import annotations

from decimal import Decimal
import unittest
import uuid

from fastapi import HTTPException

from app.models.product import PriceList, PriceListItem, Product
from app.models.settings import BranchSettings
from app.schemas.pricing import (
    PriceOverrideIntent,
    PricingCalculateRequest,
    PricingLineRequest,
)
from app.services.pricing_service import PricingService, canonical_hash, q2


class _FakeDb:
    def __init__(self, settings: BranchSettings | None = None) -> None:
        self.settings = settings

    async def scalar(self, _statement):  # noqa: ANN001
        return self.settings


class _PricingHarness(PricingService):
    def __init__(
        self,
        product: Product,
        settings: BranchSettings | None = None,
        price_list: PriceList | None = None,
        price_item: PriceListItem | None = None,
    ) -> None:
        super().__init__(_FakeDb(settings))  # type: ignore[arg-type]
        self.product = product
        self.price_list = price_list
        self.price_item = price_item

    async def _resolve_price_list(self, **_kwargs):  # noqa: ANN003
        return self.price_list

    async def _load_product(self, *_args, **_kwargs):  # noqa: ANN002, ANN003
        return self.product, None

    async def _resolve_item_price(self, **_kwargs):  # noqa: ANN003
        if self.price_item is not None:
            return Decimal(self.price_item.price), "price_list", self.price_item
        return Decimal(self.product.selling_price), "product", None


def _product(*, price: str = "100", vat_type: str = "included", vat_rate: str = "7", cost: str = "40") -> Product:
    return Product(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        sku="WP43-TEST",
        name="WP43 Test Product",
        product_type="simple",
        selling_price=Decimal(price),
        cost_price=Decimal(cost),
        vat_type=vat_type,
        vat_rate=Decimal(vat_rate),
        is_active=True,
        is_for_sale=True,
        is_for_purchase=True,
    )


def _request(
    product: Product,
    *,
    expected: str = "100",
    line_discount: str = "0",
    order_discount: str = "0",
    override: PriceOverrideIntent | None = None,
) -> PricingCalculateRequest:
    return PricingCalculateRequest(
        items=[
            PricingLineRequest(
                product_id=product.id,
                qty=Decimal("1"),
                expected_unit_price=Decimal(expected),
                discount_amount=Decimal(line_discount),
                price_override=override,
            )
        ],
        discount_amount=Decimal(order_discount),
        idempotency_key="wp43-test-key",
    )


class WP43PricingTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_price_and_vat_are_not_authoritative(self) -> None:
        product = _product(price="100", vat_type="included", vat_rate="7")
        result = await _PricingHarness(product).calculate(
            company_id=product.company_id,
            branch_id=uuid.uuid4(),
            brand_id=None,
            payload=_request(product, expected="1"),
        )

        self.assertEqual(result.lines[0].authoritative_unit_price, Decimal("100.0000"))
        self.assertEqual(result.total_amount, Decimal("100.00"))
        self.assertEqual(result.vat_amount, Decimal("6.54"))
        self.assertTrue(result.has_price_discrepancy)

    async def test_inclusive_exclusive_zero_and_exempt_vat(self) -> None:
        cases = (
            ("included", "7", Decimal("100.00"), Decimal("6.54")),
            ("excluded", "7", Decimal("107.00"), Decimal("7.00")),
            ("included", "0", Decimal("100.00"), Decimal("0.00")),
            ("exempt", "7", Decimal("100.00"), Decimal("0.00")),
        )
        for vat_type, vat_rate, expected_total, expected_vat in cases:
            with self.subTest(vat_type=vat_type, vat_rate=vat_rate):
                product = _product(vat_type=vat_type, vat_rate=vat_rate)
                result = await _PricingHarness(product).calculate(
                    company_id=product.company_id,
                    branch_id=uuid.uuid4(),
                    brand_id=None,
                    payload=_request(product),
                )
                self.assertEqual(result.total_amount, expected_total)
                self.assertEqual(result.vat_amount, expected_vat)

    async def test_combined_line_and_order_discount_drives_threshold(self) -> None:
        product = _product()
        result = await _PricingHarness(product).calculate(
            company_id=product.company_id,
            branch_id=uuid.uuid4(),
            brand_id=None,
            payload=_request(product, line_discount="10", order_discount="10"),
        )

        self.assertEqual(result.line_discount_amount, Decimal("10.00"))
        self.assertEqual(result.order_discount_amount, Decimal("10.00"))
        self.assertEqual(result.discount_amount, Decimal("20.00"))
        self.assertEqual(result.discount_percentage, Decimal("20.00"))
        self.assertEqual(result.total_amount, Decimal("80.00"))

    async def test_override_threshold_and_hard_limit(self) -> None:
        product = _product()
        settings = BranchSettings(
            company_id=product.company_id,
            branch_id=uuid.uuid4(),
            pos_price_override_auto_limit_pct=Decimal("10"),
            pos_price_override_auto_limit_amount=Decimal("100"),
            pos_price_override_max_deviation_pct=Decimal("50"),
            pos_price_override_min_margin_pct=Decimal("0"),
        )
        harness = _PricingHarness(product, settings)
        allowed = await harness.calculate(
            company_id=product.company_id,
            branch_id=settings.branch_id,
            brand_id=None,
            payload=_request(
                product,
                override=PriceOverrideIntent(requested_unit_price=Decimal("80"), reason="UAT approved"),
            ),
        )
        self.assertTrue(allowed.requires_price_override_approval)
        self.assertEqual(allowed.lines[0].applied_unit_price, Decimal("80.0000"))

        with self.assertRaises(HTTPException) as caught:
            await harness.calculate(
                company_id=product.company_id,
                branch_id=settings.branch_id,
                brand_id=None,
                payload=_request(
                    product,
                    override=PriceOverrideIntent(requested_unit_price=Decimal("40"), reason="Too low"),
                ),
            )
        self.assertEqual(caught.exception.detail["code"], "price_override_limit_exceeded")

    async def test_override_amount_threshold_requires_approval(self) -> None:
        product = _product(price="1000", cost="100")
        settings = BranchSettings(
            company_id=product.company_id,
            branch_id=uuid.uuid4(),
            pos_price_override_auto_limit_pct=Decimal("20"),
            pos_price_override_auto_limit_amount=Decimal("50"),
            pos_price_override_max_deviation_pct=Decimal("50"),
            pos_price_override_min_margin_pct=Decimal("0"),
        )
        result = await _PricingHarness(product, settings).calculate(
            company_id=product.company_id,
            branch_id=settings.branch_id,
            brand_id=None,
            payload=_request(
                product,
                override=PriceOverrideIntent(
                    requested_unit_price=Decimal("940"),
                    reason_code="price_match",
                    reason="Competitor price match",
                ),
            ),
        )
        self.assertTrue(result.requires_price_override_approval)

    async def test_effective_promotion_is_server_resolved_and_snapshotted(self) -> None:
        product = _product(price="100")
        price_list = PriceList(
            id=uuid.uuid4(),
            company_id=product.company_id,
            name="Lunch promotion",
            currency="THB",
            price_kind="promotion",
            promotion_code="LUNCH20",
            version=3,
            is_default=False,
            is_active=True,
        )
        price_item = PriceListItem(
            id=uuid.uuid4(),
            company_id=product.company_id,
            price_list_id=price_list.id,
            product_id=product.id,
            price=Decimal("80"),
            min_qty=Decimal("1"),
        )
        result = await _PricingHarness(
            product,
            price_list=price_list,
            price_item=price_item,
        ).calculate(
            company_id=product.company_id,
            branch_id=uuid.uuid4(),
            brand_id=None,
            payload=_request(product, expected="80"),
        )
        self.assertEqual(result.total_amount, Decimal("80.00"))
        self.assertEqual(result.promotion_discount_amount, Decimal("20.00"))
        self.assertEqual(result.lines[0].promotion_code, "LUNCH20")
        self.assertEqual(result.lines[0].price_list_version, 3)

    async def test_unknown_tax_context_fails_closed(self) -> None:
        product = _product(vat_type="mystery")
        with self.assertRaises(HTTPException) as caught:
            await _PricingHarness(product).calculate(
                company_id=product.company_id,
                branch_id=uuid.uuid4(),
                brand_id=None,
                payload=_request(product),
            )
        self.assertEqual(caught.exception.detail["code"], "tax_context_invalid")

    async def test_stale_price_version_is_machine_readable(self) -> None:
        product = _product()
        request = _request(product)
        request.items[0].expected_price_version = "old-version"
        with self.assertRaises(HTTPException) as caught:
            await _PricingHarness(product).calculate(
                company_id=product.company_id,
                branch_id=uuid.uuid4(),
                brand_id=None,
                payload=request,
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.detail["code"], "stale_price")

    def test_rounding_and_canonical_hash_are_deterministic(self) -> None:
        self.assertEqual(q2(Decimal("1.005")), Decimal("1.01"))
        self.assertEqual(canonical_hash({"b": 2, "a": Decimal("1.00")}), canonical_hash({"a": Decimal("1.00"), "b": 2}))


if __name__ == "__main__":
    unittest.main()
