from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal as D
from types import SimpleNamespace as NS
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.utils.business_documents import render_po_html, render_gr_html, render_payment_voucher_html
from app.utils.pdf_generator import generate_payment_voucher_pdf
from app.utils.payroll_calculator import calc_annual_pit
from app.schemas.purchase import POItemCreate
from app.services.purchase_service import PurchaseService


def fixtures(count: int = 2):
    company = ("บริษัท ตัวอย่างเอกสาร จำกัด", "63/5 หมู่ 7 ตำบลไทรน้อย จังหวัดนนทบุรี 11150", "0000000000000")
    items = [NS(product_name=f"วัตถุดิบตัวอย่างสำหรับทดสอบเอกสาร {i}", sku=f"DEMO-{i:03}",
                qty_ordered=D("5.125"), unit_code="กก.", unit_cost=D("100"), discount_amount=D("12.50"),
                subtotal=D("500"), vat_type="excluded", vat_rate=D("7"), vat_amount=D("35")) for i in range(1, count + 1)]
    po = NS(po_number="PO-DEMO-001", order_date=date(2026, 10, 12), created_at=datetime(2026, 10, 13), expected_date=None,
            status="draft", supplier=NS(name="ผู้จำหน่ายตัวอย่าง", tax_id="0000000000000", payment_term_days=30),
            items=items, subtotal=D(500) * count, discount_amount=D("12.50") * count,
            vat_amount=D(35) * count, wht_amount=D(0), total_amount=D(535) * count,
            note="ข้อมูลสมมติสำหรับตรวจแม่แบบเท่านั้น ไม่ใช่ธุรกรรมจริง", internal_note="SECRET-INTERNAL")
    gr = NS(gr_number="GR-DEMO-001", received_date=date(2026, 10, 13), location=NS(name="คลังตัวอย่าง"),
            receiver=NS(display_name="ผู้รับสินค้าทดสอบ", username="tester"), note="รับสินค้าเพื่อทดสอบแม่แบบ",
            items=[NS(po_item=item, qty_received=D("2.125"), unit_cost=item.unit_cost, note="ตรวจรับแล้ว") for item in items])
    payment = NS(payment_number="PV-DEMO-001", payment_date=date(2026, 10, 13), payment_method="transfer",
                 reference_no="TEST-ONLY", total_amount=D(1040), note="ข้อมูลสมมติ ไม่ใช่หลักฐานการจ่ายเงินจริง")
    allocations = [NS(invoice_number=f"INV-DEMO-{i}", supplier_name=f"ผู้จำหน่าย {i}", allocated_amount=D(535), wht_amount=D(15)) for i in range(1, 3)]
    return company, po, gr, payment, allocations


class BusinessDocumentTests(unittest.TestCase):
    def test_po_uses_order_date_and_does_not_invent_due_date(self):
        company, po, *_ = fixtures()
        html = render_po_html(po, *company)
        self.assertIn("12/10/2569", html)
        self.assertNotIn("13/10/2569", html)
        self.assertIn("กำหนดรับ:</strong> -", html)
        self.assertIn("ฉบับร่าง", html)
        self.assertNotIn("SECRET-INTERNAL", html)

    def test_all_templates_escape_user_content(self):
        company, po, gr, payment, allocations = fixtures()
        attack = '<img src="https://example.invalid/private" onerror="alert(1)">'
        po.items[0].product_name = attack
        gr.items[0].note = attack
        allocations[0].supplier_name = attack
        for html in (render_po_html(po, attack, *company[1:]), render_gr_html(gr, po, *company),
                     render_payment_voucher_html(payment, allocations, *company)):
            self.assertNotIn("<img", html)
            self.assertIn("&lt;img", html)
            self.assertNotIn("@import", html)

    def test_po_preserves_historical_rate_total_and_discount(self):
        company, po, *_ = fixtures(1)
        po.items[0].vat_rate, po.items[0].vat_amount = D(10), D(50)
        po.vat_amount, po.total_amount = D(50), D("541.23")
        html = render_po_html(po, *company)
        self.assertIn("10%", html)
        self.assertIn("541.23", html)
        self.assertIn("ไม่หักซ้ำ", html)
        self.assertEqual(po.total_amount, D("541.23"))

    def test_po_included_vat_not_added_twice(self):
        company, po, *_ = fixtures(1)
        po.items[0].vat_type = "included"
        html = render_po_html(po, *company)
        self.assertIn('class="num">500.00</td></tr>', html)
        self.assertIn("รวม VAT 7%", html)

    def test_gr_preserves_fractional_quantity_and_thai_date(self):
        company, po, gr, *_ = fixtures()
        html = render_gr_html(gr, po, *company)
        self.assertIn("2.125", html)
        self.assertIn("13/10/2569", html)
        self.assertIn("ผู้ตรวจสอบ", html)

    def test_exemption_is_not_labelled_as_a_percentage(self):
        company, po, *_ = fixtures(1)
        po.items[0].vat_type = "exempt"
        po.items[0].vat_amount = D(0)
        html = render_po_html(po, *company)
        self.assertIn("ยกเว้น VAT</small>", html)
        self.assertNotIn("ยกเว้น VAT 7%", html)

    def test_voucher_lists_each_supplier_and_stored_net_total(self):
        company, _, _, payment, allocations = fixtures()
        html = render_payment_voucher_html(payment, allocations, *company)
        self.assertIn("ผู้จำหน่าย 1", html)
        self.assertIn("ผู้จำหน่าย 2", html)
        self.assertIn("1,040.00", html)
        self.assertIn("30.00", html)
        self.assertIn("0000000000000", html)

    def test_common_pagination_and_empty_documents(self):
        company, po, gr, payment, _ = fixtures(0)
        for html in (render_po_html(po, *company), render_gr_html(gr, po, *company),
                     render_payment_voucher_html(payment, [], *company)):
            self.assertIn("table-header-group", html)
            self.assertIn("counter(pages)", html)
            self.assertIn("business-documents-1", html)
            self.assertIn("ไม่ใช่ใบกำกับภาษี", html)

    def test_current_pit_bands_and_allowances_are_not_replaced_by_old_excel(self):
        # RD: employment expense 50%, max 100,000; personal allowance 60,000.
        self.assertEqual(calc_annual_pit(D(300000)), D("0.00"))
        self.assertEqual(calc_annual_pit(D(500000)), D("11500.00"))
        self.assertEqual(calc_annual_pit(D(1160000)), D("115000.00"))


class PurchaseTaxRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_zero_rate_is_respected_in_totals(self):
        service = PurchaseService(MagicMock())
        for vat_type in ("included", "excluded", "exempt"):
            item = POItemCreate(product_id=uuid.uuid4(), qty_ordered=1, unit_cost=100, vat_rate=0, vat_type=vat_type)
            result = await service._calc_po_totals([item], "excluded", D(7), D(0))
            self.assertEqual(result["vat_amount"], D("0.00"))
            self.assertEqual(result["total_amount"], D("100.00"))

    async def test_standard_rate_included_excluded_and_discount(self):
        service = PurchaseService(MagicMock())
        for kind, price, discount, expected in [("excluded", 110, 10, 107), ("included", 117, 10, 107)]:
            item = POItemCreate(product_id=uuid.uuid4(), qty_ordered=1, unit_cost=price, discount_amount=discount, vat_rate=7, vat_type=kind)
            result = await service._calc_po_totals([item], kind, D(7), D(0))
            self.assertEqual(result["vat_amount"], D("7.00"))
            self.assertEqual(result["total_amount"], D(expected))

    async def test_zero_rate_persists_into_prepared_items(self):
        item = POItemCreate(product_id=uuid.uuid4(), qty_ordered=1, unit_cost=100, vat_rate=0)
        product = NS(id=item.product_id, name="Zero rated", sku="ZERO", unit=NS(code="EA"), vat_rate=D(7))
        db = MagicMock()
        db.scalar = AsyncMock(return_value=product)
        result = await PurchaseService(db)._prepare_po_items(uuid.uuid4(), [item], "excluded")
        self.assertEqual(result[0]["vat_rate"], D("0.00"))
        self.assertEqual(result[0]["vat_amount"], D("0.0000"))

    async def test_withholding_excludes_included_vat(self):
        item = POItemCreate(product_id=uuid.uuid4(), qty_ordered=1, unit_cost=107, vat_rate=7, vat_type="included")
        result = await PurchaseService(MagicMock())._calc_po_totals([item], "included", D(7), D(3))
        self.assertEqual(result["wht_amount"], D("3.00"))
        self.assertEqual(result["total_amount"], D("104.00"))

    async def test_mixed_vat_modes_withholding_and_totals(self):
        items = [POItemCreate(product_id=uuid.uuid4(), qty_ordered=1, unit_cost=price, vat_rate=rate, vat_type=kind)
                 for price, rate, kind in [(107, 7, "included"), (100, 7, "excluded"), (50, 0, "excluded")]]
        result = await PurchaseService(MagicMock())._calc_po_totals(items, "excluded", D(7), D(3))
        self.assertEqual(result["vat_amount"], D("14.00"))
        self.assertEqual(result["wht_amount"], D("7.50"))
        self.assertEqual(result["total_amount"], D("256.50"))

    async def test_payment_generator_uses_shared_template_and_preserves_renderer_result(self):
        company, _, _, payment, allocations = fixtures()
        with patch("app.utils.pdf_generator.html_to_pdf_or_html", return_value=(b"pdf", "application/pdf")) as render:
            self.assertEqual(await generate_payment_voucher_pdf(payment, allocations, *company), (b"pdf", "application/pdf"))
            self.assertIn("business-documents-1", render.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
