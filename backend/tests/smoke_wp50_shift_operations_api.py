from __future__ import annotations

import asyncio
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.main import app
from app.models.accounting import JournalEntry
from app.models.audit import AuditLog
from app.models.pos import CashierShift, PosCashMovement
from tests.smoke_approval_api import MANAGER_PIN, PASSWORD, expect, expect_detail_code, issue_approval, login, prepare


async def verify(shift_id: str) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        shift = await db.get(CashierShift, uuid.UUID(shift_id))
        if shift is None or shift.status != "closed" or shift.version != 4:
            raise RuntimeError("WP50 shift did not close at the expected version")
        if shift.expected_cash != Decimal("1600.00") or shift.closing_cash != Decimal("2100.00"):
            raise RuntimeError("WP50 server cash summary was not persisted")
        if shift.cash_difference != Decimal("500.00") or shift.close_reason_code != "count_over":
            raise RuntimeError("WP50 variance evidence is incomplete")
        if shift.close_snapshot_json is None or shift.close_snapshot_json.get("can_close") is not True:
            raise RuntimeError("WP50 immutable close snapshot is missing")
        movement_ids = list((await db.scalars(select(PosCashMovement.id).where(PosCashMovement.shift_id == shift.id))).all())
        if len(movement_ids) != 2:
            raise RuntimeError(f"Expected exactly two cash movements, got {len(movement_ids)}")
        journals = int(await db.scalar(select(func.count(JournalEntry.id)).where(
            JournalEntry.reference_type == "PosCashMovement",
            JournalEntry.reference_id.in_([str(value) for value in movement_ids]),
        )) or 0)
        if journals != 2:
            raise RuntimeError(f"Expected exactly two cash movement journals, got {journals}")
        close_audits = int(await db.scalar(select(func.count(AuditLog.id)).where(
            AuditLog.resource == "CashierShift",
            AuditLog.resource_id == str(shift.id),
            AuditLog.action == "pos.shift.close",
        )) or 0)
        if close_audits != 1:
            raise RuntimeError(f"Expected one close audit, got {close_audits}")
    await engine.dispose()


def run() -> None:
    context = asyncio.run(prepare())
    with TestClient(app) as client:
        cashier = login(client, context["cashier_username"])
        manager = login(client, context["manager_username"])
        expect(client.put("/api/v1/approvals/manager-pin", headers=manager, json={"current_password": PASSWORD, "pin": MANAGER_PIN}), 200)

        open_payload = {
            "location_id": context["location_id"],
            "opening_cash": "500",
            "shift_type": "staff_cashier",
            "idempotency_key": f"wp50-open-{uuid.uuid4()}",
        }
        shift = expect(client.post("/api/v1/pos/shifts/open", headers=cashier, json=open_payload), 201)
        replay_open = expect(client.post("/api/v1/pos/shifts/open", headers=cashier, json=open_payload), 201)
        if replay_open["id"] != shift["id"]:
            raise RuntimeError("Open-shift retry created a duplicate")

        summary = expect(client.get(f"/api/v1/pos/shifts/{shift['id']}/summary", headers=cashier), 200)
        if summary["expected_cash"] != "500.00" or not summary["can_close"]:
            raise RuntimeError(f"Unexpected initial shift summary: {summary}")

        first_movement = {
            "movement_type": "cash_in",
            "amount": "100",
            "reason_code": "change_fund",
            "reason": "เติมเงินทอนทดสอบ WP50",
            "expected_shift_version": summary["version"],
            "idempotency_key": f"wp50-movement-a-{uuid.uuid4()}",
        }
        movement_a = expect(client.post(f"/api/v1/pos/shifts/{shift['id']}/cash-movements", headers=cashier, json=first_movement), 201)
        replay_a = expect(client.post(f"/api/v1/pos/shifts/{shift['id']}/cash-movements", headers=cashier, json=first_movement), 201)
        if replay_a["id"] != movement_a["id"]:
            raise RuntimeError("Cash movement retry created a duplicate")

        second_movement = {
            "movement_type": "cash_in",
            "amount": "1000",
            "reason_code": "change_fund",
            "reason": "เติมเงินทอนถึงเกณฑ์ Manager",
            "expected_shift_version": movement_a["shift_version"],
            "idempotency_key": f"wp50-movement-b-{uuid.uuid4()}",
        }
        expect_detail_code(client.post(f"/api/v1/pos/shifts/{shift['id']}/cash-movements", headers=cashier, json=second_movement), 403, "approval_required")
        movement_approval = expect(issue_approval(client, cashier, context, action="pos.cash_movement.approve", request_payload={"shift_id": shift["id"], **second_movement}, reason="อนุมัติเติมเงินทอน WP50"), 200)
        movement_b = expect(client.post(f"/api/v1/pos/shifts/{shift['id']}/cash-movements", headers=cashier, json={**second_movement, "approval_token": movement_approval["approval_token"]}), 201)
        replay_b = expect(client.post(f"/api/v1/pos/shifts/{shift['id']}/cash-movements", headers=cashier, json=second_movement), 201)
        if replay_b["id"] != movement_b["id"]:
            raise RuntimeError("Approved cash movement retry was not idempotent")

        summary = expect(client.get(f"/api/v1/pos/shifts/{shift['id']}/summary", headers=cashier), 200)
        if summary["expected_cash"] != "1600.00" or summary["version"] != 3 or not summary["can_close"]:
            raise RuntimeError(f"Unexpected final summary before close: {summary}")

        close_payload = {
            "closing_cash": "2100",
            "reason_code": "count_over",
            "note": "พบเงินเกินระหว่างทดสอบ WP50",
            "cash_count": [{"denomination": "1000", "quantity": 2}, {"denomination": "100", "quantity": 1}],
            "expected_version": summary["version"],
            "idempotency_key": f"wp50-close-{uuid.uuid4()}",
        }
        expect_detail_code(client.post(f"/api/v1/pos/shifts/{shift['id']}/close", headers=cashier, json=close_payload), 403, "approval_required")
        close_approval = expect(issue_approval(client, cashier, context, action="pos.shift.variance.approve", request_payload={"shift_id": shift["id"], **close_payload}, reason="อนุมัติส่วนต่างปิดกะ WP50"), 200)
        closed = expect(client.post(f"/api/v1/pos/shifts/{shift['id']}/close", headers=cashier, json={**close_payload, "approval_token": close_approval["approval_token"]}), 200)
        replay_closed = expect(client.post(f"/api/v1/pos/shifts/{shift['id']}/close", headers=cashier, json=close_payload), 200)
        if replay_closed["id"] != closed["id"]:
            raise RuntimeError("Approved close retry was not idempotent")
        expect_detail_code(client.post(f"/api/v1/pos/shifts/{shift['id']}/close", headers=cashier, json={**close_payload, "idempotency_key": f"wp50-other-{uuid.uuid4()}"}), 409, "shift_closed")

    asyncio.run(verify(shift["id"]))
    print("WP50 shift operations smoke: PASS")


if __name__ == "__main__":
    run()
