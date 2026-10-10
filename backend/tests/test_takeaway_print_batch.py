import inspect
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm.attributes import set_committed_value
from types import SimpleNamespace
from app.dependencies import TokenData
from app.models.takeaway import TakeawayOrder, TakeawayReceipt
from app.schemas.takeaway import TakeawayReceiptPrintCreate
from app.services.takeaway_service import TakeawayService
from app.routers.takeaway import mark_order_receipt_printed, list_receipts

class PrintBatchTests(unittest.IsolatedAsyncioTestCase):
    def setup_flow(self):
        self.current = TokenData(user_id=uuid.uuid4(), company_id=uuid.uuid4(), brand_id=uuid.uuid4(), branch_id=uuid.uuid4(), business_type="takeaway", target_database="takeaway", permissions=["takeaway.sale.create"])
        c = self.current
        self.order = TakeawayOrder(id=uuid.uuid4(), company_id=c.company_id, brand_id=c.brand_id, branch_id=c.branch_id)
        self.receipt = TakeawayReceipt(id=uuid.uuid4(), order_id=self.order.id, company_id=c.company_id, branch_id=c.branch_id, receipt_number="TEST", print_count=0, payload={"tax_amount": "7", "total_amount": "107"})
        self.events = set(); self.db = AsyncMock(); self.db.get.return_value = self.order
        def scalar(stmt):
            if "FROM takeaway_receipts" in str(stmt): return self.receipt
            params = stmt.compile().params
            return uuid.uuid4() if any(v in self.events for v in params.values() if isinstance(v, str)) else None
        self.db.scalar.side_effect = scalar
        self.service = TakeawayService(self.db, c)
        self.service._outbox = MagicMock(side_effect=lambda **kw: self.events.add(kw["idempotency_key"]))

    async def test_batch_audits_each_copy_once_same_identity_preserves_merchant_and_tax(self):
        self.setup_flow(); batch = uuid.uuid4()
        for copy in ("customer", "preparation"):
            data = TakeawayReceiptPrintCreate(copy_type=copy, batch_id=batch, idempotency_key="fixture-key")
            _, replay = await self.service.mark_receipt_printed(self.order.id, data); self.assertFalse(replay)
            _, replay = await self.service.mark_receipt_printed(self.order.id, data); self.assertTrue(replay)
        self.assertEqual(self.receipt.print_count, 2); self.assertEqual(self.db.commit.await_count, 2)
        self.assertEqual(len(self.events), 2)
        self.assertEqual(self.receipt.payload["print_copies"]["preparation"]["batch_id"], str(batch))
        self.assertEqual(self.receipt.payload["tax_amount"], "7"); self.assertEqual(self.receipt.payload["total_amount"], "107")
        await self.service.mark_receipt_printed(self.order.id, TakeawayReceiptPrintCreate(copy_type="merchant", idempotency_key="legacy-copy"))
        self.assertEqual(self.receipt.last_printed_copy, "merchant")
        self.assertEqual(self.receipt.payload["print_copies"]["merchant"]["count"], 1)

    async def test_reprint_new_batch_counts_once_and_history_never_renames_merchant(self):
        self.setup_flow()
        for _ in range(2):
            await self.service.mark_receipt_printed(self.order.id, TakeawayReceiptPrintCreate(copy_type="preparation", batch_id=uuid.uuid4(), idempotency_key="fixture-key"))
        self.assertEqual(self.receipt.payload["print_copies"]["preparation"]["count"], 2)
        self.assertNotIn("merchant", self.receipt.payload["print_copies"])

    async def test_scope_checked_before_idempotency_replay_and_mutation(self):
        for field in ("company_id", "brand_id", "branch_id"):
            self.setup_flow(); setattr(self.order, field, uuid.uuid4())
            with self.assertRaises(HTTPException) as error:
                await self.service.mark_receipt_printed(self.order.id, TakeawayReceiptPrintCreate(copy_type="preparation", idempotency_key="fixture-key"))
            self.assertEqual(error.exception.status_code, 404); self.db.commit.assert_not_awaited()

    async def test_idempotency_lookup_occurs_under_receipt_row_lock(self):
        self.setup_flow()
        await self.service.mark_receipt_printed(self.order.id, TakeawayReceiptPrintCreate(copy_type="preparation", idempotency_key="fixture-key"))
        sql = str(self.db.scalar.call_args_list[0].args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        self.assertIn("FOR UPDATE", sql); self.assertIn(str(self.current.company_id), sql)
        self.assertIn("takeaway_operational_outbox", str(self.db.scalar.call_args_list[1].args[0]))

    async def test_receipt_history_is_tenant_brand_branch_scoped(self):
        self.setup_flow(); self.db.scalars.return_value = []
        await self.service.list_receipts()
        sql = str(self.db.scalars.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for value in (str(self.current.company_id), str(self.current.brand_id), str(self.current.branch_id), "DESC", "LIMIT 50"):
            self.assertIn(value, sql)

    async def test_legacy_receipt_projects_canonical_notes_without_rewriting_snapshot(self):
        self.setup_flow()
        self.order.note = "ไม่เผ็ด"
        set_committed_value(self.receipt, "payload", dict(self.receipt.payload))
        self.db.scalars.return_value = [SimpleNamespace(sku="PORK", name="หมูย่าง", quantity=2, note="ไม่ใส่ผัก")]
        result = await self.service.get_receipt(self.order.id)
        self.assertEqual(result.payload["note"], "ไม่เผ็ด")
        self.assertEqual(result.payload["preparation_items"], [{"sku": "PORK", "name": "หมูย่าง", "quantity": "2", "note": "ไม่ใส่ผัก"}])
        self.assertEqual(result.payload["tax_amount"], "7")
        self.assertFalse(sa_inspect(result).attrs.payload.history.has_changes())
        self.db.commit.assert_not_awaited()

    async def test_history_and_print_route_permissions_are_distinct(self):
        self.setup_flow(); self.current.permissions = ["takeaway.sale.view"]
        read = inspect.signature(list_receipts).parameters["current"].default.dependency
        write = inspect.signature(mark_order_receipt_printed).parameters["current"].default.dependency
        self.assertIs(await read(self.current), self.current)
        with self.assertRaises(HTTPException): await write(self.current)
