from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


TWOPLACES = Decimal("0.01")


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def build_financial_reconciliation(
    *,
    source_sales_total: Decimal,
    branch_rows_total: Decimal,
    source_payment_total: Decimal,
) -> dict[str, dict[str, Decimal | bool]]:
    sales_source = _money(source_sales_total)
    branch_total = _money(branch_rows_total)
    payment_total = _money(source_payment_total)
    sales_delta = _money(branch_total - sales_source)
    payment_delta = _money(payment_total - sales_source)
    return {
        "sales": {
            "source_order_total": sales_source,
            "branch_rows_total": branch_total,
            "delta": sales_delta,
            "is_reconciled": abs(sales_delta) <= TWOPLACES,
        },
        "payments": {
            "source_payment_total": payment_total,
            "source_order_total": sales_source,
            "delta": payment_delta,
            "is_reconciled": abs(payment_delta) <= TWOPLACES,
        },
    }
