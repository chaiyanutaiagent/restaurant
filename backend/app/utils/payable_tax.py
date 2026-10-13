"""Payment-time WHT. Invoice subtotal is net of VAT; amounts are THB.

Existing pre-withheld invoices are deliberately not converted automatically.
Partial payments apportion the VAT-exclusive value using cumulative rounding.
"""
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def payment_tax(invoice, item) -> dict:
    def reject(message: str):
        raise HTTPException(status_code=409, detail=message)

    if money(invoice.wht_amount) != 0:
        reject("ใบแจ้งหนี้เดิมหัก WHT ตอนตั้งหนี้แล้ว กรุณาให้บัญชีตรวจทานก่อนจ่ายต่อ เพื่อป้องกันหักซ้ำ")
    if invoice.status not in {"unpaid", "partial"}:
        reject("ใบแจ้งหนี้นี้จ่ายแล้วหรือยกเลิกแล้ว")
    subtotal, vat = money(invoice.subtotal), money(invoice.vat_amount)
    gross, paid, remaining = map(money, (invoice.total_amount, invoice.paid_amount, invoice.remaining_amount))
    if subtotal < 0 or vat < 0 or gross <= 0 or gross != subtotal + vat or paid < 0 or remaining != gross - paid:
        reject("ยอดใบแจ้งหนี้ไม่สอดคล้อง กรุณาให้บัญชีตรวจทานก่อนจ่าย")
    allocated, rate = money(item.allocated_amount), money(item.wht_rate)
    if allocated <= 0 or allocated > remaining:
        reject("ยอดตัดหนี้ต้องมากกว่า 0 และไม่เกินยอดค้าง")
    if not 0 <= rate <= 100:
        reject("อัตรา WHT ต้องอยู่ระหว่าง 0 ถึง 100")
    max_base = money(subtotal * (paid + allocated) / gross) - money(subtotal * paid / gross)
    requested_base = getattr(item, "wht_base_amount", None)
    base = money(requested_base) if requested_base is not None else (max_base if rate > 0 else Decimal("0.00"))
    if base < 0 or base > max_base or (rate == 0 and base != 0) or (rate > 0 and base <= 0):
        reject("ฐาน WHT ต้องไม่เกินมูลค่าไม่รวม VAT ของการจ่ายครั้งนี้ และต้องสอดคล้องกับอัตรา")
    income_type = (item.wht_type or "").strip()
    if not income_type:
        reject("ระบุประเภทเงินได้ หรือเหตุผลที่ไม่หัก WHT")
    wht = money(base * rate / 100)
    supplied_wht = getattr(item, "wht_amount", None)
    if supplied_wht is not None and money(supplied_wht) != wht:
        reject("ยอด WHT ไม่ตรงกับที่ระบบคำนวณ กรุณาตรวจยอดใหม่")
    return dict(invoice_id=invoice.id, allocated_amount=allocated, vat_exclusive_amount=max_base,
                wht_base_amount=base, wht_rate=rate, wht_amount=wht, wht_type=income_type,
                net_amount=allocated - wht)
