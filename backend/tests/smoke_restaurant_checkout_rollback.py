"""Opt-in UAT checkout regression; all writes use rollback-only outer transactions."""
import asyncio
import os
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import active_identity_session_factory, active_restaurant_service_session_factory, get_identity_db, get_restaurant_service_db
from app.main import app
from app.models.pos import SaleOrder, Payment, CashierShift
from app.models.restaurant import DiningSession, DiningOrder, DiningOrderItem, DiningTable
from app.models.user import User
from app.services.auth_service import AuthService


async def main():
    assert settings.environment == 'development' and 'uat-' in settings.saas_public_base_url
    assert settings.identity_database == 'platform_core' and settings.restaurant_service_database == 'legacy'
    session_id = uuid.UUID(os.environ['UAT_CHECKOUT_SESSION_ID'])
    identity, operational = active_identity_session_factory(), active_restaurant_service_session_factory()
    async def snapshot():
        async with operational() as db:
            assert await db.scalar(text('select current_database()')) == 'restaurant_uat_db'
            session = await db.get(DiningSession, session_id)
            counts = [await db.scalar(select(func.count()).select_from(model)) for model in
                      (SaleOrder, Payment, CashierShift, DiningSession, DiningOrder, DiningOrderItem)]
            table = await db.get(DiningTable, session.table_id)
            return (counts, session.status, session.sale_order_id, session.closed_at, table.status)
    baseline = await snapshot()
    assert baseline[1] == 'bill_requested' and baseline[2] is None
    async with identity.kw['bind'].connect() as identity_conn, operational.kw['bind'].connect() as conn:
        identity_tx, tx = await identity_conn.begin(), await conn.begin()
        async def identity_db():
            async with AsyncSession(bind=identity_conn, expire_on_commit=False, join_transaction_mode='create_savepoint') as db:
                yield db
        async def restaurant_db():
            async with AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode='create_savepoint') as db:
                yield db
        app.dependency_overrides[get_identity_db] = identity_db
        app.dependency_overrides[get_restaurant_service_db] = restaurant_db
        try:
            async with AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode='create_savepoint') as db:
                session = await db.get(DiningSession, session_id)
                sale = await db.scalar(select(SaleOrder).where(SaleOrder.company_id == session.company_id,
                    SaleOrder.client_order_id == f'restaurant-session-{session_id}'))
                assert sale and sale.status == 'completed'
                sale_id, user_id, branch_id = sale.id, sale.user_id, session.branch_id
                expected_total, paid, change = sale.total_amount, sale.paid_amount, sale.change_amount
                assert expected_total == Decimal('45') and paid == Decimal('100') and change == Decimal('55')
                # Clone only the dining input to exercise a first checkout, not only replay.
                clone_id = uuid.uuid4()
                db.add(DiningSession(id=clone_id, company_id=session.company_id, branch_id=branch_id,
                    table_id=session.table_id, status='bill_requested', queue_number=90001))
                await db.flush()
                orders = (await db.scalars(select(DiningOrder).where(DiningOrder.session_id == session_id))).all()
                for order in orders:
                    values = {c.name: getattr(order, c.name) for c in DiningOrder.__table__.columns
                              if c.name not in {'id', 'session_id', 'order_number', 'idempotency_key'}}
                    cloned = DiningOrder(**values, session_id=clone_id, order_number=f'UAT-{uuid.uuid4().hex[:12]}')
                    db.add(cloned)
                    await db.flush()
                    items = (await db.scalars(select(DiningOrderItem).where(DiningOrderItem.order_id == order.id))).all()
                    for item in items:
                        values = {c.name: getattr(item, c.name) for c in DiningOrderItem.__table__.columns
                                  if c.name not in {'id', 'order_id'}}
                        db.add(DiningOrderItem(**values, order_id=cloned.id))
                await db.commit()
            async with AsyncSession(bind=identity_conn, expire_on_commit=False, join_transaction_mode='create_savepoint') as db:
                owner = await db.get(User, user_id)
                assert owner and not owner.is_superuser
                access, _ = await AuthService(db).create_session(owner, None, '127.0.0.1', 'rollback-only checkout regression')
            # Block external notifications during the synthetic first checkout.
            with patch('app.services.sale_service.trigger_event', new=AsyncMock()), patch('app.services.sale_service.NotificationService.notify_event', new=AsyncMock()):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://uat-app.foodchainservice.com', headers={'Authorization': 'Bearer ' + access}) as client:
                    switched = await client.post('/api/v1/auth/switch-branch', json={'branch_id': str(branch_id)})
                    assert switched.status_code == 200, switched.text[:300]
                    client.headers['Authorization'] = 'Bearer ' + switched.json()['data']['access_token']
                    payload = {'payment_method': 'cash', 'paid_amount': 100, 'discount_amount': 0}
                    url = f'/api/v1/restaurant/sessions/{session_id}/checkout'
                    mismatch = await client.post(url, json={**payload, 'paid_amount': '101'})
                    assert mismatch.status_code == 409, mismatch.text[:500]
                    recovered = await client.post(url, json=payload)
                    assert recovered.status_code == 200, recovered.text[:500]
                    data = recovered.json()['data']
                    assert data['sale_order_id'] == str(sale_id) and Decimal(data['change_amount']) == change
                    assert data['table_name'] == 'A 1'
                    repeat = await client.post(url, json=payload)
                    assert repeat.status_code == 400, repeat.text[:500]
                    fresh = await client.post(f'/api/v1/restaurant/sessions/{clone_id}/checkout', json=payload)
                    assert fresh.status_code == 200, fresh.text[:500]
                    assert fresh.json()['data']['sale_order_id'] != str(sale_id)
                    async with AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode='create_savepoint') as db:
                        for sid in (session_id, clone_id):
                            sales = (await db.scalars(select(SaleOrder).where(SaleOrder.client_order_id == f'restaurant-session-{sid}'))).all()
                            assert len(sales) == 1
                            assert await db.scalar(select(func.count(Payment.id)).where(Payment.order_id == sales[0].id)) == 1
                            closed = await db.get(DiningSession, sid)
                            assert closed.status == 'closed' and closed.sale_order_id == sales[0].id
                    print('PASS: changed payment 409; original sale reused 200; repeat blocked 400; first checkout 200 despite missing account; exactly one sale/payment per session')
            assert identity_tx.is_active and tx.is_active
        finally:
            app.dependency_overrides.clear()
            await tx.rollback()
            await identity_tx.rollback()
    assert await snapshot() == baseline
    print('PASS: rollback preserved real A1, payment, shift and all sale/dining counts')


if __name__ == '__main__':
    asyncio.run(main())
