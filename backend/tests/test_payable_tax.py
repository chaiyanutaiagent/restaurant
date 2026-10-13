"""Focused payment/WHT regression tests. No external database or real writes."""
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace as NS
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import hashlib
import json

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.models.payable import APPayment, APPaymentAllocation, WHTCertificate, SupplierInvoice
from app.schemas.payable import SupplierInvoiceCreate, PaymentAllocationInput, CreateAPPaymentRequest
from app.services.payable_service import PayableService
from app.utils.payable_tax import payment_tax
from app.utils.pdf_generator import generate_wht_certificate_pdf


def invoice(**changes):
    values = dict(id=uuid.uuid4(), company_id=uuid.uuid4(), branch_id=uuid.uuid4(), supplier_id=uuid.uuid4(),
                  subtotal=D("1000"), vat_amount=D("70"), wht_amount=D(0), total_amount=D("1070"),
                  paid_amount=D(0), remaining_amount=D("1070"), status="unpaid", invoice_date=date(2026, 10, 1))
    values.update(changes)
    return NS(**values)


def allocation(inv, **changes):
    values = dict(invoice_id=inv.id, allocated_amount=inv.remaining_amount, wht_rate=D(3), wht_type="ค่าบริการ")
    values.update(changes)
    return PaymentAllocationInput(**values)


def request(inv, *rows):
    return CreateAPPaymentRequest(idempotency_key=uuid.uuid4(), branch_id=inv.branch_id, payment_date=date(2026, 10, 13),
                                  payment_method="bank_transfer", wht_reviewed=True,
                                  allocations=list(rows) or [allocation(inv)])


class PaymentTaxTests(TestCase):
    def test_vat_excluded_and_net_cash(self):
        inv = invoice()
        result = payment_tax(inv, allocation(inv))
        self.assertEqual((result["wht_base_amount"], result["wht_amount"], result["net_amount"]), (D(1000), D(30), D(1040)))

    def test_partial_payments(self):
        inv = invoice()
        first = payment_tax(inv, allocation(inv, allocated_amount=D(535)))
        inv.paid_amount, inv.remaining_amount, inv.status = D(535), D(535), "partial"
        last = payment_tax(inv, allocation(inv))
        self.assertEqual(first["wht_base_amount"], D(500))
        self.assertEqual(last["wht_amount"] + first["wht_amount"], D(30))

    def test_vat_zero_and_other_rate_not_hardcoded_seven(self):
        for vat in [D(0), D(100), D(35)]:
            inv = invoice(vat_amount=vat, total_amount=1000 + vat, remaining_amount=1000 + vat)
            self.assertEqual(payment_tax(inv, allocation(inv))["wht_amount"], D(30))

    def test_income_subset(self):
        inv = invoice()
        result = payment_tax(inv, allocation(inv, wht_base_amount=D(400)))
        self.assertEqual(result["wht_amount"], D(12))

    def test_no_withholding_requires_reason(self):
        inv = invoice()
        result = payment_tax(inv, allocation(inv, wht_rate=0, wht_type="ซื้อสินค้าทั่วไป ไม่หัก"))
        self.assertEqual((result["wht_amount"], result["wht_base_amount"], result["net_amount"]), (D(0), D(0), D(1070)))
        with self.assertRaises(HTTPException):
            payment_tax(inv, allocation(inv, wht_rate=0, wht_type=" "))

    def test_legacy_prebooked_is_blocked_without_mutation(self):
        inv = invoice(wht_amount=D(30), total_amount=D(1040), remaining_amount=D(1040))
        original = vars(inv).copy()
        for rate in [0, 3]:
            with self.assertRaisesRegex(HTTPException, "ตั้งหนี้"):
                payment_tax(inv, allocation(inv, wht_rate=rate))
        self.assertEqual(vars(inv), original)

    def test_stale_or_tampered_client_amount_rejected(self):
        inv = invoice()
        for value in [0, 32.10, 31, 30.01]:
            with self.assertRaises(HTTPException):
                payment_tax(inv, allocation(inv, wht_amount=value))
        self.assertEqual(payment_tax(inv, allocation(inv, wht_amount=30))["wht_amount"], D(30))

    def test_base_cannot_include_vat_or_exceed_proportional_share(self):
        inv = invoice()
        for change in [dict(wht_base_amount=1070), dict(allocated_amount=535, wht_base_amount=501), dict(wht_rate=0, wht_base_amount=1000)]:
            with self.assertRaises(HTTPException):
                payment_tax(inv, allocation(inv, **change))

    def test_cumulative_base_rounding_and_last_cent(self):
        inv = invoice(subtotal=D("1"), vat_amount=D("0.07"), total_amount=D("1.07"), remaining_amount=D("1.07"))
        bases = []
        for part in [D("0.35"), D("0.36"), D("0.36")]:
            bases.append(payment_tax(inv, allocation(inv, allocated_amount=part))["wht_base_amount"])
            inv.paid_amount += part
            inv.remaining_amount -= part
        self.assertEqual(sum(bases), D(1))
        inv = invoice(paid_amount=D("1069.99"), remaining_amount=D("0.01"), status="partial")
        self.assertEqual(payment_tax(inv, allocation(inv))["allocated_amount"], D("0.01"))

    def test_invalid_invoice_and_overpayment(self):
        for inv in [invoice(status="paid"), invoice(status="cancelled"), invoice(total_amount=D(999)), invoice(remaining_amount=D(100))]:
            with self.assertRaises(HTTPException):
                payment_tax(inv, allocation(inv))
        inv = invoice()
        with self.assertRaises(HTTPException):
            payment_tax(inv, allocation(inv, allocated_amount=1070.01))

    def test_schema_rejects_negative_nonfinite_and_excess_precision(self):
        inv = invoice()
        for patch_value in [dict(allocated_amount=-1), dict(allocated_amount="NaN"), dict(wht_rate=101), dict(wht_rate=-3), dict(allocated_amount="1.001"), dict(wht_amount="Infinity")]:
            with self.assertRaises(ValidationError):
                allocation(inv, **patch_value)

    def test_new_invoice_cannot_pre_withhold(self):
        fields = dict(supplier_id=uuid.uuid4(), branch_id=uuid.uuid4(), invoice_date=date.today(), subtotal=1000, vat_amount=70)
        self.assertEqual(SupplierInvoiceCreate(**fields).wht_amount, D(0))
        with self.assertRaises(ValidationError):
            SupplierInvoiceCreate(**fields, wht_amount=30)

    def test_review_required(self):
        inv = invoice()
        payload = request(inv).model_dump()
        payload["wht_reviewed"] = False
        with self.assertRaises(ValidationError):
            CreateAPPaymentRequest(**payload)


class PaymentServiceTests(IsolatedAsyncioTestCase):
    def setup_service(self, inv):
        snapshot_patch = patch("app.services.payable_service.capture_payment_snapshots", new_callable=AsyncMock)
        self.capture = snapshot_patch.start()
        self.addCleanup(snapshot_patch.stop)
        db = MagicMock()
        db.flush, db.commit, db.scalar, db.scalars, db.execute = [AsyncMock() for _ in range(5)]
        db.scalar.return_value = None
        service = PayableService(db)
        service._validate_branch = AsyncMock()
        db.scalars.return_value = NS(all=lambda: [inv])
        service._generate_running_number = AsyncMock(side_effect=["PAY-TEST", "WHT-TEST", "WHT-TEST-2"])
        service.get_payment = AsyncMock(return_value=NS(id=uuid.uuid4()))
        return db, service

    async def test_snapshot_failure_never_commits_payment(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        self.capture.side_effect = RuntimeError("Evidence storage unavailable")
        with patch("app.services.payable_service.AccountingService") as accounting:
            accounting.return_value._post_entry = AsyncMock()
            with self.assertRaises(RuntimeError):
                await service.create_payment(inv.company_id, uuid.uuid4(), request(inv))
        self.capture.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_same_request_returns_existing_payment_without_posting(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        data = request(inv)
        payment_id = uuid.uuid4()
        fingerprint = hashlib.sha256(json.dumps(data.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
        db.scalar.return_value = NS(branch_id=inv.branch_id, new_value={"fingerprint": fingerprint, "payment_id": str(payment_id)})
        result = await service.create_payment(inv.company_id, uuid.uuid4(), data)
        self.assertEqual(result, service.get_payment.return_value)
        service.get_payment.assert_awaited_once_with(payment_id, inv.company_id)
        db.add.assert_not_called()
        db.scalars.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_same_key_changed_payload_rejected(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        db.scalar.return_value = NS(branch_id=inv.branch_id, new_value={"fingerprint": "old", "payment_id": str(uuid.uuid4())})
        with self.assertRaises(HTTPException):
            await service.create_payment(inv.company_id, uuid.uuid4(), request(inv))
        db.add.assert_not_called()

    async def test_cancellation_keeps_reversal_in_same_transaction(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        db.scalar.side_effect = [inv, uuid.uuid4()]
        service.get_invoice = AsyncMock(return_value=inv)
        with patch("app.services.payable_service.AccountingService") as accounting, patch("app.services.payable_service.append_event", new_callable=AsyncMock) as event:
            accounting.return_value.reverse_entry = AsyncMock()
            await service.cancel_invoice(inv.id, inv.company_id, uuid.uuid4(), "บันทึกผิด")
            self.assertEqual(event.call_args.args[5], "บันทึกผิด")
            self.assertFalse(accounting.return_value.reverse_entry.call_args.kwargs["commit"])
        db.commit.assert_awaited_once()
        self.assertEqual(inv.status, "cancelled")

    async def test_certificate_failure_never_commits_payment(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        service._generate_running_number.side_effect = ["PAY-TEST", RuntimeError("certificate failure")]
        with patch("app.services.payable_service.AccountingService") as accounting:
            accounting.return_value._post_entry = AsyncMock()
            with self.assertRaises(RuntimeError):
                await service.create_payment(inv.company_id, uuid.uuid4(), request(inv))
        db.commit.assert_not_awaited()

    async def test_payment_posting_and_certificate_share_exact_tax_basis(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        with patch("app.services.payable_service.AccountingService") as accounting:
            post = accounting.return_value._post_entry = AsyncMock()
            await service.create_payment(inv.company_id, uuid.uuid4(), request(inv))
        added = [call.args[0] for call in db.add.call_args_list]
        payment = next(item for item in added if isinstance(item, APPayment))
        alloc = next(item for item in added if isinstance(item, APPaymentAllocation))
        cert = next(item for item in added if isinstance(item, WHTCertificate))
        self.assertEqual(payment.total_amount, D(1040))
        self.assertEqual(alloc.wht_amount, cert.wht_amount)
        self.assertEqual(cert.base_amount, D(1000))
        self.assertEqual(inv.remaining_amount, D(0))
        self.assertEqual(inv.status, "paid")
        lines = post.call_args.kwargs["lines"]
        self.assertEqual(sum(line.debit_amount for line in lines), sum(line.credit_amount for line in lines))
        self.assertEqual([line.credit_amount for line in lines if line.account_code == "2103"], [D(30)])
        db.commit.assert_awaited_once()
        sql = str(db.scalars.call_args.args[0].compile(dialect=postgresql.dialect()))
        self.assertIn("FOR UPDATE OF supplier_invoices", sql)
        self.assertIn("supplier_invoices.branch_id", sql)
        self.assertIn("supplier_invoices.company_id", sql)

    async def test_preview_writes_nothing(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        result = await service.preview_payment(inv.company_id, request(inv))
        self.assertEqual(result["net_amount"], D(1040))
        db.add.assert_not_called()
        db.commit.assert_not_awaited()
        self.assertNotIn("FOR UPDATE", str(db.scalars.call_args.args[0]))

    async def test_prebooked_and_tampered_requests_create_nothing(self):
        for inv, amount in [(invoice(wht_amount=D(30)), None), (invoice(), D("32.10"))]:
            db, service = self.setup_service(inv)
            with self.assertRaises(HTTPException):
                await service.create_payment(inv.company_id, uuid.uuid4(), request(inv, allocation(inv, wht_amount=amount)))
            db.add.assert_not_called()
            db.commit.assert_not_awaited()

    async def test_no_wht_no_certificate(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        with patch("app.services.payable_service.AccountingService") as accounting:
            accounting.return_value._post_entry = AsyncMock()
            await service.create_payment(inv.company_id, uuid.uuid4(), request(inv, allocation(inv, wht_rate=0, wht_type="ซื้อสินค้า")))
        self.assertFalse(any(isinstance(call.args[0], WHTCertificate) for call in db.add.call_args_list))

    async def test_one_cent_remaining_not_written_off(self):
        inv = invoice()
        db, service = self.setup_service(inv)
        with patch("app.services.payable_service.AccountingService") as accounting:
            accounting.return_value._post_entry = AsyncMock()
            await service.create_payment(inv.company_id, uuid.uuid4(), request(inv, allocation(inv, allocated_amount=D("1069.99"))))
        self.assertEqual(inv.remaining_amount, D("0.01"))
        self.assertEqual(inv.status, "partial")

    async def test_duplicate_missing_cross_supplier_and_backdate_rejected(self):
        inv = invoice()
        for mode in ["duplicate", "missing", "supplier", "backdate"]:
            db, service = self.setup_service(inv)
            data = request(inv)
            if mode == "duplicate":
                data.allocations *= 2
            elif mode == "missing":
                db.scalars.return_value = NS(all=lambda: [])
            elif mode == "supplier":
                second = invoice()
                data.allocations.append(allocation(second))
                db.scalars.return_value = NS(all=lambda: [inv, second])
            else:
                data.payment_date = date(2026, 9, 1)
            with self.assertRaises(HTTPException):
                await service.create_payment(inv.company_id, uuid.uuid4(), data)
            db.add.assert_not_called()

    async def test_number_lock_is_stable_across_companies_and_gaps(self):
        db = MagicMock(execute=AsyncMock(), flush=AsyncMock(), scalars=AsyncMock(return_value=NS(all=lambda: ["WHT20261013-0001", "WHT20261013-0005"])))
        service = PayableService(db)
        for company in [uuid.uuid4(), uuid.uuid4()]:
            number = await service._generate_running_number(WHTCertificate, company, "certificate_number", "WHT", date(2026, 10, 13))
            self.assertEqual(number, "WHT20261013-0006")
        self.assertEqual(db.execute.call_args_list[0].args[1], db.execute.call_args_list[1].args[1])

    async def test_certificate_uses_stored_base_and_escapes_names(self):
        cert = NS(certificate_number="WHT-OLD", wht_type="<img src=x>", issue_date=date(2026, 10, 1), base_amount=D("123.45"), wht_rate=D(3), wht_amount=D("3.70"))
        with patch("app.utils.pdf_generator.html_to_pdf_or_html", side_effect=lambda html: (html, "text/html")):
            html, _ = await generate_wht_certificate_pdf(cert, "<script>x</script>", "123", "Company", "123", "Address")
        self.assertIn("123.45", html)
        self.assertIn("3.70", html)
        self.assertIn("ไม่รวม VAT", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
