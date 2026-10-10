import inspect
import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql
from app.dependencies import TokenData
from app.models.takeaway import TakeawayOrder, TakeawayKitchenTicket
from app.services.takeaway_service import TakeawayService
from app.services.takeaway_fulfillment_policy import configured_counter_mode
from app.services.mobile_store_policy import enforce_store_request
from app.routers.takeaway import counter_order_action


class CounterFlowTests(unittest.IsolatedAsyncioTestCase):
    def setup_flow(self, state="queued", mode="counter_combined"):
        self.current = TokenData(user_id=uuid.uuid4(), company_id=uuid.uuid4(), brand_id=uuid.uuid4(), branch_id=uuid.uuid4(),
            business_type="takeaway", target_database="takeaway", permissions=["takeaway.sale.create"])
        c = self.current
        self.order = TakeawayOrder(id=uuid.uuid4(), company_id=c.company_id, brand_id=c.brand_id, branch_id=c.branch_id,
            order_number="UAT13-FIXTURE", queue_number=4, status="paid", fulfillment_status=state, source_metadata={})
        self.ticket = TakeawayKitchenTicket(id=uuid.uuid4(), company_id=c.company_id, brand_id=c.brand_id, branch_id=c.branch_id, status=state)
        self.db = AsyncMock()
        self.db.scalar.side_effect = lambda stmt: self.order if "FROM takeaway_orders" in str(stmt) else None
        self.db.scalars.return_value = [self.ticket]
        self.platform = AsyncMock(); self.platform.scalar.return_value = {"takeaway_fulfillment_mode": mode}
        self.service = TakeawayService(self.db, c); self.service._validate_context = AsyncMock(); self.service._outbox = MagicMock()

    async def action(self, action):
        return await self.service.counter_order_action(self.order.id, action, self.platform)

    async def test_accept_then_handoff_and_duplicate_or_late_taps_no_second_event(self):
        self.setup_flow()
        await self.action("accept"); await self.action("accept")
        self.assertEqual(self.order.fulfillment_status, "ready"); self.assertEqual(self.ticket.status, "ready")
        self.assertEqual(self.service._outbox.call_count, 1)
        await self.action("handoff"); await self.action("handoff"); await self.action("accept")
        self.assertEqual(self.order.fulfillment_status, "picked_up")
        self.assertIsNotNone(self.order.picked_up_at)
        self.assertEqual(self.service._outbox.call_count, 2); self.assertEqual(self.db.commit.await_count, 2)
        self.assertEqual([h["status"] for h in self.order.source_metadata["fulfillment_history"]], ["ready", "picked_up"])

    async def test_legacy_preparing_handoff_normalizes_tickets_and_audits_atomically(self):
        self.setup_flow("preparing")
        await self.action("handoff")
        self.assertEqual(self.order.fulfillment_status, "picked_up"); self.assertEqual(self.ticket.status, "ready")
        self.assertEqual(self.db.commit.await_count, 1)
        self.assertEqual([h["status"] for h in self.order.source_metadata["fulfillment_history"]], ["ready", "picked_up"])
        self.assertEqual(self.order.source_metadata["fulfillment_history"][0]["from_status"], "preparing")

    async def test_ready_handoff_and_queued_cannot_skip_accept(self):
        self.setup_flow("ready"); await self.action("handoff")
        self.assertEqual(self.service._outbox.call_count, 1)
        self.setup_flow()
        with self.assertRaises(HTTPException) as error: await self.action("handoff")
        self.assertEqual(error.exception.status_code, 409); self.db.commit.assert_not_awaited()

    async def test_other_workflows_and_unconfigured_mode_fail_closed(self):
        for mode in ("separate_stations", "unknown", None):
            self.setup_flow(mode=mode)
            with self.assertRaises(HTTPException) as error: await self.action("accept")
            self.assertEqual(error.exception.status_code, 409); self.db.commit.assert_not_awaited()
        self.setup_flow(mode="separate_stations")
        await self.service.update_fulfillment_order(self.order.id, "preparing")
        self.assertEqual(self.order.fulfillment_status, "preparing")
        with self.assertRaises(HTTPException): await self.service.mark_picked_up(self.order.id)

    async def test_branch_brand_tenant_and_permission_guards(self):
        for field in ("brand_id", "branch_id"):
            self.setup_flow(); setattr(self.order, field, uuid.uuid4())
            with self.assertRaises(HTTPException) as error: await self.action("accept")
            self.assertEqual(error.exception.status_code, 404); self.platform.scalar.assert_not_awaited()
        self.setup_flow(); self.db.scalar.side_effect = None; self.db.scalar.return_value = None
        with self.assertRaises(HTTPException) as error: await self.action("accept")
        self.assertEqual(error.exception.status_code, 404)
        sql = str(self.db.scalar.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        self.assertIn(str(self.current.company_id), sql); self.assertIn("FOR UPDATE", sql)
        self.setup_flow(); self.current.permissions = ["takeaway.catalog.view"]
        with self.assertRaises(HTTPException) as error: await self.action("accept")
        self.assertEqual(error.exception.status_code, 403); self.db.scalar.assert_not_awaited()

    async def test_action_permissions_are_specific_and_paid_guard_remains(self):
        self.setup_flow(); self.current.permissions = ["takeaway.pickup.manage"]
        with self.assertRaises(HTTPException): await self.action("accept")
        self.setup_flow("ready"); self.current.permissions = ["takeaway.kitchen.manage"]
        with self.assertRaises(HTTPException): await self.action("handoff")
        for state in ("draft", "cancelled", "refunded"):
            self.setup_flow(); self.order.status = state
            with self.assertRaises(HTTPException): await self.action("accept")
            self.db.commit.assert_not_awaited()

    async def test_active_query_filters_before_limit_and_keeps_old_queues(self):
        self.setup_flow(); self.db.scalars.return_value = []
        await self.service.list_orders(active_only=True, limit=500)
        sql = str(self.db.scalars.call_args.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        for value in (str(self.current.company_id), str(self.current.brand_id), str(self.current.branch_id), "queued", "preparing", "ready", "paid", "ASC", "LIMIT 500"):
            self.assertIn(value, sql)
        self.assertNotIn("'picked_up'", sql)

    async def test_route_permission_and_signed_store_allowlist(self):
        self.setup_flow()
        dependency = inspect.signature(counter_order_action).parameters["current"].default.dependency
        self.assertIs(await dependency(self.current), self.current)
        self.current.permissions = ["takeaway.catalog.view"]
        with self.assertRaises(HTTPException): await dependency(self.current)
        claims = {"client_surface": "takeaway_store", "company_id": str(self.current.company_id), "branch_id": str(self.current.branch_id), "store_device_id": "device"}
        headers = {"x-company-id": claims["company_id"], "x-branch-id": claims["branch_id"], "x-store-device-id": "device"}
        for action in ("accept", "handoff"):
            enforce_store_request(claims, "POST", f"/api/v1/takeaway/counter/orders/{self.order.id}/{action}", headers)
        with self.assertRaises(HTTPException): enforce_store_request(claims, "POST", f"/api/v1/takeaway/counter/orders/{self.order.id}/accept", {**headers, "x-company-id": "wrong"})

    def test_explicit_branch_override_wins_over_brand_default(self):
        branch = uuid.uuid4()
        self.assertFalse(configured_counter_mode({}, branch))
        self.assertFalse(configured_counter_mode({"takeaway_fulfillment_mode": "counter_combined", "takeaway_branch_fulfillment_modes": {str(branch): "separate_stations"}}, branch))
        self.assertTrue(configured_counter_mode({"takeaway_branch_fulfillment_modes": {str(branch): "counter_combined"}}, branch))
