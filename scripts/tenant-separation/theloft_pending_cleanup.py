"""Owner-authorized UAT fixture cleanup; default is a transactional rehearsal.

Run inside the deployed backend. Never touches Takeaway or Retail databases.
Archives exact rows, rejects unknown incoming dependencies, and verifies that
every other public row (including stock and completed orders) is unchanged.
"""
import asyncio
import json
import os
import uuid
from collections import defaultdict

from sqlalchemy import text
from app.database import engine
from app.config import settings

C = '1b8a1818-44d6-4d5f-9d22-e5e17b23c081'
ARCH = 'uat_theloft_pending_cleanup_20261025'
ROOTS = {
    'company_production_orders': ['af7fcd7f-0a15-5085-ac3c-33de62522448', 'eafd88af-7012-5e38-97c1-82574eb5cc2a'],
    'company_production_demands': ['0b9a4982-e92e-5687-9d1b-1fb179ec57fe', '560adef4-13bf-53b4-853e-e3dc46cb83c0'],
    'company_distribution_shipments': ['e04e1329-3638-5f4d-b8ac-c7abdbbed98a'],
    'company_distribution_demands': ['c4818f54-d598-5f04-8e16-e539a420a037'],
    'transfer_orders': ['27d83e48-a9d7-5db7-9c8a-ae3a9a485c39'],
}
ALLOWED = set(ROOTS) | {'company_production_inputs', 'company_distribution_events', 'transfer_order_items'}

def inside(col, values):
    for value in values:
        uuid.UUID(value)
    return f'"{col}"::text IN (' + ','.join("'" + x + "'" for x in sorted(values)) + ')' if values else 'false'

async def rows(c, sql):
    return (await c.execute(text(sql))).mappings().all()

async def digest(c, table, where='true'):
    return await c.scalar(text(f'''SELECT md5(coalesce(string_agg(h,'' ORDER BY h),''))
        FROM (SELECT md5(to_jsonb(x)::text) h FROM public."{table}" x WHERE {where}) s'''))

async def main():
    apply = os.environ.get('THELOFT_PENDING_APPLY') == 'YES'
    assert settings.environment == 'development'
    async with engine.connect() as c:
        tx = await c.begin()
        try:
            assert await c.scalar(text('select current_database()')) == 'restaurant_uat_db'
            if apply:
                assert os.environ.get('THELOFT_PENDING_BACKUP_VERIFIED') == 'YES'
            await c.execute(text("SET LOCAL lock_timeout='8s'"))
            await c.execute(text('LOCK TABLE ' + ','.join('"' + t + '"' for t in sorted(ALLOWED)) + ' IN SHARE ROW EXCLUSIVE MODE'))
            cols = defaultdict(set)
            for r in await rows(c, "select table_name,column_name from information_schema.columns where table_schema='public'"):
                cols[r['table_name']].add(r['column_name'])
            fks = await rows(c, '''select ch.relname child,pa.relname parent,a.attname col
                from pg_constraint f join pg_class ch on ch.oid=f.conrelid
                join pg_class pa on pa.oid=f.confrelid
                join pg_attribute a on a.attrelid=f.conrelid and a.attnum=f.conkey[1]
                where f.contype='f' and f.connamespace='public'::regnamespace and cardinality(f.conkey)=1''')
            target = defaultdict(set, {t: set(ids) for t, ids in ROOTS.items()})
            for table, ids in ROOTS.items():
                assert await c.scalar(text(f'SELECT count(*) FROM "{table}" WHERE {inside("id", ids)} AND company_id=\'{C}\'')) == len(ids), table
            assert not await c.scalar(text(f'SELECT count(*) FROM company_kitchen_movements WHERE {inside("production_order_id", target["company_production_orders"])}'))
            assert not await c.scalar(text(f'''SELECT count(*) FROM company_production_orders
                WHERE {inside('id', target['company_production_orders'])}
                AND (status NOT IN ('planned','in_progress') OR actual_output_qty IS NOT NULL OR total_input_cost<>0)'''))
            assert not await c.scalar(text(f'''SELECT count(*) FROM company_distribution_shipments
                WHERE {inside('id', target['company_distribution_shipments'])}
                AND (status<>'planned' OR shipped_qty<>0 OR received_qty<>0 OR rejected_qty<>0 OR returned_qty<>0)'''))
            assert await c.scalar(text(f'SELECT status FROM transfer_orders WHERE {inside("id", target["transfer_orders"])}')) == 'draft'
            for _ in range(20):
                changed = False
                for f in fks:
                    if not target.get(f['parent']):
                        continue
                    found = await rows(c, f'SELECT id FROM "{f["child"]}" WHERE {inside(f["col"], target[f["parent"]])}')
                    if not found:
                        continue
                    assert f['child'] in ALLOWED, f'Unreviewed dependency: {f["child"]}'
                    new = {str(r['id']) for r in found} - target[f['child']]
                    changed |= bool(new)
                    target[f['child']].update(new)
                if not changed:
                    break
            else:
                raise AssertionError('Dependency closure did not converge')
            target = {t: ids for t, ids in target.items() if ids}
            where = {t: inside('id', ids) for t, ids in target.items()}
            for t, cond in where.items():
                if 'company_id' in cols[t]:
                    assert not await c.scalar(text(f'SELECT count(*) FROM "{t}" WHERE ({cond}) AND company_id<>\'{C}\'')), t
            edges = defaultdict(set)
            for f in fks:
                if f['parent'] in target and f['child'] in target and f['child'] != f['parent']:
                    edges[f['parent']].add(f['child'])
            remaining = set(target)
            order = []
            while remaining:
                ready = sorted(t for t in remaining if not edges[t] & remaining)
                assert ready, 'Dependency cycle'
                order.extend(ready)
                remaining.difference_update(ready)
            protected = {t: await digest(c, t, 'NOT (' + where[t] + ')' if t in where else 'true') for t in cols}
            assert not await c.scalar(text(f"SELECT count(*) FROM pg_namespace WHERE nspname='{ARCH}'")), 'Already applied'
            await c.execute(text(f'CREATE SCHEMA "{ARCH}"'))
            for t, cond in where.items():
                await c.execute(text(f'CREATE TABLE "{ARCH}"."{t}" AS SELECT * FROM public."{t}" WHERE {cond}'))
            counts = {}
            for t in order:
                result = await c.execute(text(f'DELETE FROM public."{t}" WHERE {where[t]}'))
                assert result.rowcount == len(target[t]), t
                counts[t] = result.rowcount
            for t, old in protected.items():
                assert old == await digest(c, t, 'NOT (' + where[t] + ')' if t in where else 'true'), f'Protected rows changed: {t}'
            if apply:
                await tx.commit()
            else:
                await tx.rollback()
            print(json.dumps({'mode': 'APPLIED' if apply else 'REHEARSED_AND_ROLLED_BACK', 'removed': counts,
                              'archive_schema': ARCH, 'protected_tables': len(protected),
                              'stock_unchanged': True, 'completed_orders_unchanged': True}), flush=True)
        except BaseException:
            if tx.is_active:
                await tx.rollback()
            raise

if __name__ == '__main__':
    asyncio.run(main())
