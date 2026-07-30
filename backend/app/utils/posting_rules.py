from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

TWOPLACES = Decimal("0.01")


def q2(value: Decimal | int | float | str) -> Decimal:
    return Decimal(value).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class PostingLine:
    account_code: str
    debit_amount: Decimal
    credit_amount: Decimal
    description: str


def get_sale_posting(
    subtotal: Decimal,
    vat_amount: Decimal,
    total_amount: Decimal,
    payment_method: str,
    discount_amount: Decimal = Decimal("0"),
) -> list[PostingLine]:
    cash_account = "1103" if payment_method == "credit_card" else "1101"
    revenue_amount = q2(Decimal(subtotal) - Decimal(discount_amount))
    return [
        PostingLine(
            account_code=cash_account,
            debit_amount=q2(total_amount),
            credit_amount=Decimal("0.00"),
            description="รับชำระค่าสินค้า",
        ),
        PostingLine(
            account_code="4001",
            debit_amount=Decimal("0.00"),
            credit_amount=revenue_amount,
            description="รายได้จากการขายสินค้า",
        ),
        PostingLine(
            account_code="2102",
            debit_amount=Decimal("0.00"),
            credit_amount=q2(vat_amount),
            description="ภาษีขาย",
        ),
    ]


def get_purchase_posting(
    subtotal: Decimal,
    vat_amount: Decimal,
    wht_amount: Decimal,
    total_amount: Decimal,
    is_inventory: bool = True,
) -> list[PostingLine]:
    purchase_account = "1105" if is_inventory else "6006"
    lines = [
        PostingLine(
            account_code=purchase_account,
            debit_amount=q2(subtotal),
            credit_amount=Decimal("0.00"),
            description="รับสินค้าหรือค่าใช้จ่าย",
        ),
        PostingLine(
            account_code="1104",
            debit_amount=q2(vat_amount),
            credit_amount=Decimal("0.00"),
            description="ภาษีซื้อ",
        ),
        PostingLine(
            account_code="2101",
            debit_amount=Decimal("0.00"),
            credit_amount=q2(total_amount),
            description="เจ้าหนี้การค้า",
        ),
    ]
    if q2(wht_amount) > 0:
        lines.append(
            PostingLine(
                account_code="2103",
                debit_amount=Decimal("0.00"),
                credit_amount=q2(wht_amount),
                description="ภาษีหัก ณ ที่จ่ายค้างจ่าย",
            )
        )
    return lines


def get_payment_posting(
    amount: Decimal,
    payment_method: str,
) -> list[PostingLine]:
    del payment_method
    return [
        PostingLine(
            account_code="1101",
            debit_amount=q2(amount),
            credit_amount=Decimal("0.00"),
            description="รับเงินสดหรือเงินโอน",
        ),
        PostingLine(
            account_code="1103",
            debit_amount=Decimal("0.00"),
            credit_amount=q2(amount),
            description="ตัดลูกหนี้การค้า",
        ),
    ]


def get_stock_adjustment_posting(
    qty_delta: Decimal,
    cost_per_unit: Decimal,
) -> list[PostingLine]:
    value = q2(abs(Decimal(qty_delta) * Decimal(cost_per_unit)))
    if value == 0:
        return []
    if Decimal(qty_delta) > 0:
        return [
            PostingLine(
                account_code="1105",
                debit_amount=value,
                credit_amount=Decimal("0.00"),
                description="ปรับเพิ่มสินค้าคงเหลือ",
            ),
            PostingLine(
                account_code="6006",
                debit_amount=Decimal("0.00"),
                credit_amount=value,
                description="ปรับปรุงมูลค่าสินค้าคงเหลือ",
            ),
        ]
    return [
        PostingLine(
            account_code="6006",
            debit_amount=value,
            credit_amount=Decimal("0.00"),
            description="ตัดค่าใช้จ่ายจากการปรับสต็อก",
        ),
        PostingLine(
            account_code="1105",
            debit_amount=Decimal("0.00"),
            credit_amount=value,
            description="ลดสินค้าคงเหลือ",
        ),
    ]
