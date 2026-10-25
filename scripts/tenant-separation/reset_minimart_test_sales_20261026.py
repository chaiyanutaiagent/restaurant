"""One-off, owner-approved UAT sales reset; stock MUST stay unchanged.

Run inside the UAT backend. Default is read-only. Review the signature before
--apply, and supply --backup-ref only after verified Retail + Platform dumps.
Never use for production or as a general-purpose tenant reset.
Retains stock ledger, audit logs, pricing evidence, reporting receipt tombstones,
the new empty shift, users, products, devices and all other stores.
"""
import argparse
import asyncio
import hashlib
import json

from sqlalchemy import text

from app.config import settings
from app.database import platform_engine, retail_engine

COMPANY = '9b766136-c10f-4ef4-856f-b2f95b943f5e'
BRANCH = 'cc8e47e0-6e02-5783-8401-180c5061717c'
SHIFT = '50a936cb-1a7d-4cda-a122-f7ff94012c4e'
ORDERS = (
    'aef0741d-a974-4a39-b04a-300bbc8a757b',
    'bc355203-ffcf-418f-beb4-7e55e747aad6',
    'c886c090-039a-40b7-83fd-c6859f6430b6',
)
ARCHIVE = 'uat_minimart_sales_reset_20261026'
EXPECTED = {'retail': 'retail_ops_db', 'platform': 'restaurant_platform_core_db'}


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def in_ids(column, values):
    return column + '::text IN (' + ','.join("'" + str(v).replace("'", "''") + "'" for v in values) + ')'


SCOPE = f"x.company_id='{COMPANY}' AND x.branch_id='{BRANCH}'"
SELECTION = {
    'retail': {
        'payments': in_ids('x.order_id', ORDERS),
        'sale_order_items': in_ids('x.order_id', ORDERS),
        'operational_outbox_events': in_ids('x.aggregate_id', ORDERS) + " AND x.aggregate_type='SaleOrder'",
        'sale_orders': in_ids('x.id', ORDERS),
        'cashier_shifts': f"x.id='{SHIFT}'",
    },
    'platform': {
        'company_reporting_facts': in_ids('x.source_document_id', ORDERS)
        + f" AND {SCOPE} AND x.source_stream='retail_pos' AND x.module_key='retail_pos'",
    },
}
COUNTS = {'retail': {'payments': 3, 'sale_order_items': 4, 'operational_outbox_events': 3,
                     'sale_orders': 3, 'cashier_shifts': 1},
          'platform': {'company_reporting_facts': 3}}
PROTECTED = {
    'retail': ['stock_balances', 'stock_movements', 'products', 'product_variants',
               'product_images', 'categories', 'units', 'users', 'brands', 'branches',
               'brand_branches', 'stock_locations', 'audit_logs', 'price_calculations'],
    'platform': ['company_reporting_event_receipts', 'device_registrations', 'users',
                 'staff_role_assignments', 'brands', 'branches', 'brand_branches'],
}


async def fingerprint(connection, table, predicate='true'):
    result = await connection.execute(text(
        f"SELECT count(*), md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM "
        f"(SELECT md5(to_jsonb(x)::text) h FROM public.{quote(table)} x WHERE {predicate}) s"))
    return list(result.one())


async def plan(connection, label):
    selected = {}
    for table, predicate in SELECTION[label].items():
        selected[table] = await fingerprint(connection, table, predicate)
        assert selected[table][0] == COUNTS[label][table], f'Unexpected count: {label}/{table}'
        assert not await connection.scalar(text(
            f"SELECT count(*) FROM {quote(table)} x WHERE ({predicate}) AND x.company_id<>'{COMPANY}'"))
    # Fail closed on any unreviewed referencing row, even ON DELETE CASCADE.
    fks = (await connection.execute(text("""
        SELECT ch.relname child, pa.relname parent,
          array_agg(a.attname ORDER BY u.ord) cc, array_agg(b.attname ORDER BY u.ord) pc
        FROM pg_constraint f JOIN pg_class ch ON ch.oid=f.conrelid
        JOIN pg_class pa ON pa.oid=f.confrelid
        JOIN LATERAL unnest(f.conkey,f.confkey) WITH ORDINALITY u(c,p,ord) ON true
        JOIN pg_attribute a ON a.attrelid=f.conrelid AND a.attnum=u.c
        JOIN pg_attribute b ON b.attrelid=f.confrelid AND b.attnum=u.p
        WHERE f.contype='f' AND f.connamespace='public'::regnamespace
        GROUP BY f.oid,ch.relname,pa.relname
    """))).mappings()
    for fk in fks:
        if fk['parent'] not in SELECTION[label]:
            continue
        joins = ' AND '.join(f'c.{quote(a)}=x.{quote(b)}' for a, b in zip(fk['cc'], fk['pc']))
        child_predicate = SELECTION[label].get(fk['child'], 'false').replace('x.', 'c.')
        n = await connection.scalar(text(
            f"SELECT count(*) FROM {quote(fk['child'])} c JOIN {quote(fk['parent'])} x ON {joins} "
            f"WHERE ({SELECTION[label][fk['parent']]}) AND NOT ({child_predicate})"))
        assert not n, f"Unreviewed dependency {label}/{fk['child']} -> {fk['parent']}"
    if label == 'retail':
        assert await connection.scalar(text(f"SELECT count(*) FROM sale_orders x WHERE {SCOPE}")) == 3
        assert await connection.scalar(text(
            f"SELECT count(*) FROM sale_orders x WHERE {SCOPE} AND status='completed' "
            f"AND shift_id='{SHIFT}' AND refund_amount=0 AND NOT is_offline")) == 3
        assert str(await connection.scalar(text(f'SELECT sum(total_amount) FROM sale_orders x WHERE {SCOPE}'))) == '125.00'
        assert await connection.scalar(text(f"SELECT status FROM cashier_shifts WHERE id='{SHIFT}'")) == 'closed'
        for table in ['journal_entries', 'tax_documents']:
            # Logical references are not necessarily protected by a foreign key.
            cols = set((await connection.execute(text(
                'SELECT column_name FROM information_schema.columns WHERE table_schema=\'public\' AND table_name=:t'), {'t': table})).scalars())
            if 'reference_id' in cols:
                assert not await connection.scalar(text(f'SELECT count(*) FROM {quote(table)} x WHERE ' + in_ids('x.reference_id', ORDERS)))
    return selected


async def main(args):
    assert settings.environment == 'development', 'UAT only'
    assert settings.identity_database == 'platform_core' and settings.retail_service_database == 'retail'
    if args.apply:
        assert args.backup_ref and args.signature, 'Verified backup and reviewed signature required'
    connections, transactions, before, plans = {}, {}, {}, {}
    committed = []
    try:
        for label, engine in [('retail', retail_engine), ('platform', platform_engine)]:
            c = await engine.connect()
            connections[label] = c
            transactions[label] = await c.begin()
            assert await c.scalar(text('SELECT current_database()')) == EXPECTED[label]
            await c.execute(text("SET LOCAL lock_timeout='5s'"))
            await c.execute(text("SET LOCAL statement_timeout='30s'"))
            if not args.apply:
                await c.execute(text('SET TRANSACTION READ ONLY'))
            else:
                # Brief locks prevent sales/outbox/report writes while archiving.
                await c.execute(text('LOCK TABLE ' + ','.join('public.' + quote(t) for t in sorted(SELECTION[label])) + ' IN SHARE ROW EXCLUSIVE MODE'))
            assert not await c.scalar(text('SELECT count(*) FROM pg_namespace WHERE nspname=:n'), {'n': ARCHIVE}), 'Already applied; inspect archive before retry'
            plans[label] = await plan(c, label)
            before[label] = {t: await fingerprint(c, t) for t in PROTECTED[label]}
            before[label].update({t: await fingerprint(c, t, f'NOT ({p})') for t, p in SELECTION[label].items()})
        signature = hashlib.sha256(json.dumps(plans, sort_keys=True).encode()).hexdigest()
        print(json.dumps({'signature': signature, 'selected': plans, 'apply': args.apply}), flush=True)
        if not args.apply:
            return
        assert signature == args.signature, 'Plan changed; re-review required'
        for label, c in connections.items():
            await c.execute(text('CREATE SCHEMA ' + quote(ARCHIVE)))
            await c.execute(text(f'CREATE TABLE {quote(ARCHIVE)}.reset_manifest (created_at timestamptz DEFAULT now(), details jsonb NOT NULL)'))
            await c.execute(text(f'INSERT INTO {quote(ARCHIVE)}.reset_manifest(details) VALUES (CAST(:d AS jsonb))'),
                            {'d': json.dumps({'signature': signature, 'backup_ref': args.backup_ref,
                                              'instruction': 'Delete Mini Mart test sales; preserve current stock',
                                              'preserved_fingerprints': before[label]})})
            for table, predicate in SELECTION[label].items():
                await c.execute(text(f'CREATE TABLE {quote(ARCHIVE)}.{quote(table)} AS SELECT * FROM public.{quote(table)} x WHERE {predicate}'))
                result = await c.execute(text(f'DELETE FROM public.{quote(table)} x WHERE {predicate}'))
                assert result.rowcount == COUNTS[label][table]
            for table, expected in before[label].items():
                assert await fingerprint(c, table) == expected, f'Preservation check failed: {label}/{table}'
        # Separate DBs: source first, projection second. If the second commit
        # fails, retained receipt tombstones prevent replay; recover projection
        # from the verified backup/archive with explicit operator review.
        for label in ['retail', 'platform']:
            await transactions[label].commit()
            committed.append(label)
        print(json.dumps({'result': 'complete', 'archive': ARCHIVE, 'deleted': COUNTS,
                          'stock_preserved': True, 'other_rows_preserved': True,
                          'committed': committed, 'production_changed': False}), flush=True)
    except BaseException:
        print(json.dumps({'committed_before_error': committed}), flush=True)
        raise
    finally:
        for tx in transactions.values():
            if tx.is_active:
                await tx.rollback()
        for c in connections.values():
            await c.close()
        await retail_engine.dispose()
        await platform_engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--signature')
    parser.add_argument('--backup-ref')
    asyncio.run(main(parser.parse_args()))
