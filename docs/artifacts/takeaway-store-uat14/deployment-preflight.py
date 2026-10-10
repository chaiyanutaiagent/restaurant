"""Read-only UAT database checks; never prints connection secrets or customer rows."""
import asyncio, hashlib, json, sys
from sqlalchemy import text
from app.database import TakeawaySessionLocal

async def main():
    async with TakeawaySessionLocal() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        assert (await db.execute(text("SELECT current_database(), host(inet_server_addr())"))).one() == ("takeaway_ops_db", "172.18.0.4")
        revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == ("p6takeaway0009" if sys.argv[1] == "before" else "p6takeaway0010")
        constraints = list((await db.execute(text("SELECT conname, pg_get_constraintdef(oid), convalidated FROM pg_constraint WHERE conrelid='takeaway_receipts'::regclass AND contype='c'"))).all())
        assert any("last_printed_copy" in row[1] and row[2] for row in constraints)
        if sys.argv[1] != "before": assert any("preparation" in row[1] for row in constraints)
        invalid = await db.scalar(text("SELECT count(*) FROM takeaway_receipts WHERE last_printed_copy IS NOT NULL AND last_printed_copy NOT IN ('customer','merchant','preparation')"))
        assert invalid == 0
        queue = "b27b4470-7506-4c2e-b901-ac79b1911aaf"
        snapshots = []
        for table, key in [("takeaway_orders", "id"), ("takeaway_receipts", "order_id"), ("takeaway_order_items", "order_id"), ("takeaway_payments", "order_id")]:
            snapshots.append(await db.scalar(text(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id)::text,'[]') FROM {table} t WHERE {key}=:id"), {"id": queue}))
        digest = hashlib.sha256(json.dumps(snapshots).encode()).hexdigest()
        print(json.dumps({"revision": revision, "constraint_valid": True, "invalid_copy_rows": invalid, "queue4_snapshot_sha256": digest}))

asyncio.run(main())
