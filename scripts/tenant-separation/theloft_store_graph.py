"""Read-only dependency manifest for the three-store split (no data migration).

Never selects central stock or Retail legacy data by a branch-only predicate.
The manifest deliberately fails closed on unexpected shared dependencies.
"""
import asyncio
import json
from collections import defaultdict
from sqlalchemy import text
from app.database import engine, platform_engine, retail_engine

C = '1b8a1818-44d6-4d5f-9d22-e5e17b23c081'
B = ['3b2249b2-7f2c-4750-8eec-6bb8a3e4a3c4', '03bb1c3b-cfd3-4766-a7f7-26585192974a', 'dbbe2036-1cd0-4f15-b4c6-97c78c15fd43']
BR = ['c8f9d7bc-9b45-44f5-b799-de12fb636d72', '3f8bdf47-885d-4a38-bac0-bccd6db9f8b3', '7f87be6e-bd5e-40aa-bb94-b37e098281e1']
U = ['1ffa800e-2076-43da-a7d1-5dc9d9358470', '71aeda7d-68ee-42cd-a146-5787e9be30dc']
GLOBAL = {'companies', 'permissions', 'platform_operators'}
PARENTS = {'brands', 'branches', 'stock_locations', 'products', 'product_variants', 'categories', 'units',
           'users', 'roles', 'departments', 'positions', 'customers', 'customer_groups', 'price_lists',
           'cashier_shifts', 'dining_tables', 'dining_sessions', 'dining_orders', 'sale_orders',
           'employees', 'payroll_runs', 'recipes', 'pos_hold_drafts', 'restaurant_cancellations',
           'device_registrations', 'price_calculations', 'kitchen_tickets', 'dining_order_items'}
CHILDREN = {'dining_order_items', 'kitchen_tickets', 'restaurant_cancellations',
            'restaurant_cancellation_items', 'restaurant_cancellation_waste',
            'restaurant_cancellation_audits', 'kitchen_cancellation_events',
            'recipe_ingredients', 'product_images', 'product_variants',
            'payroll_items', 'payroll_details', 'pos_hold_draft_audits'}
OWNING_PARENT = {
    'dining_order_items': {'dining_orders'}, 'kitchen_tickets': {'dining_order_items', 'dining_orders'},
    'restaurant_cancellations': {'dining_orders', 'dining_sessions'},
    'restaurant_cancellation_items': {'restaurant_cancellations'},
    'restaurant_cancellation_waste': {'restaurant_cancellations'},
    'restaurant_cancellation_audits': {'restaurant_cancellations'},
    'kitchen_cancellation_events': {'restaurant_cancellations'},
    'recipe_ingredients': {'recipes'}, 'product_images': {'products'}, 'product_variants': {'products'},
    'payroll_items': {'payroll_runs'}, 'payroll_details': {'payroll_runs'},
    'pos_hold_draft_audits': {'pos_hold_drafts'},
}

def ins(col, values):
    return f'"{col}"::text IN (' + ','.join("'" + x + "'" for x in values) + ')' if values else 'false'

async def rows(c, sql):
    return (await c.execute(text(sql))).mappings().all()

async def inspect(eng, kind):
    async with eng.connect() as c:
        await c.execute(text('SET TRANSACTION READ ONLY'))
        cols = defaultdict(set)
        for r in await rows(c, "select table_name,column_name from information_schema.columns where table_schema='public'"):
            cols[r['table_name']].add(r['column_name'])
        fks = await rows(c, '''select ch.relname child,pa.relname parent,a.attname col,p.attname parent_col
            from pg_constraint f join pg_class ch on ch.oid=f.conrelid join pg_class pa on pa.oid=f.confrelid
            join pg_attribute a on a.attrelid=f.conrelid and a.attnum=f.conkey[1]
            join pg_attribute p on p.attrelid=f.confrelid and p.attnum=f.confkey[1]
            where f.contype='f' and f.connamespace='public'::regnamespace and cardinality(f.conkey)=1''')
        selected = defaultdict(set)
        blockers = set()
        async def add(t, condition):
            if t not in cols or 'id' not in cols[t]:
                return False
            found = {str(r['id']) for r in await rows(c, f'SELECT id FROM "{t}" WHERE {condition}')}
            new = found - selected[t]
            selected[t].update(found)
            return bool(new)
        branches = B if kind == 'platform' else B[:2] if kind == 'restaurant' else B[2:]
        brands = BR if kind == 'platform' else BR[:2] if kind == 'restaurant' else BR[2:]
        await add('branches', ins('id', branches))
        await add('brands', ins('id', brands))
        await add('brand_branches', ins('branch_id', branches) + ' AND is_active=true')
        if kind == 'platform':
            await add('users', ins('id', U))
            await add('user_branches', ins('user_id', U) + ' AND deleted_at IS NULL')
            await add('staff_role_assignments', ins('user_id', U) + ' AND revoked_at IS NULL')
        else:
            await add('branch_settings', ins('branch_id', branches))
            if kind == 'restaurant':
                await add('products', ins('brand_id', brands) + " AND product_type<>'raw_material'")
                await add('recipes', ins('brand_id', brands) + " AND recipe_type='menu_recipe'")
                for t in ['dining_tables', 'dining_sessions', 'dining_orders', 'cashier_shifts', 'pos_hold_drafts', 'employees', 'payroll_runs']:
                    await add(t, ins('branch_id', branches))
            else:
                for t in ['products', 'sale_orders', 'stock_balances', 'stock_movements', 'cashier_shifts']:
                    pred = ins('brand_id', brands) if t == 'products' else ins('branch_id', branches)
                    count = await c.scalar(text(f'SELECT count(*) FROM "{t}" WHERE {pred}'))
                    assert count == 0, f'Retail reset no longer empty: {t}'
        for _ in range(30):
            changed = False
            for f in fks:
                ch, pa, col, pc = f['child'], f['parent'], f['col'], f['parent_col']
                if selected.get(ch) and pa not in GLOBAL:
                    condition = f'"{pc}" IN (SELECT "{col}" FROM "{ch}" WHERE {ins("id", list(selected[ch]))})'
                    if pa not in PARENTS:
                        if await c.scalar(text(f'SELECT count(*) FROM "{pa}" WHERE {condition}')):
                            blockers.add(f'Unreviewed parent {ch}.{col}->{pa}')
                    else:
                        changed |= await add(pa, condition)
                if selected.get(pa) and pa in OWNING_PARENT.get(ch, set()):
                    changed |= await add(ch, ins(col, list(selected[pa])))
            if not changed:
                break
        else:
            blockers.add('Dependency closure did not converge')
        # Cloning a shared location's definition is safe; its balances are NOT selected.
        # A new tenant may never acquire an unrelated brand/branch through history.
        for table, allowed in [('brands', brands), ('branches', branches)]:
            unexpected = selected[table] - set(allowed)
            if unexpected:
                blockers.add(f'Outside-scope {table}: ' + ','.join(sorted(unexpected)))
        for t, ids in selected.items():
            if ids and 'company_id' in cols[t]:
                count = await c.scalar(text(f'SELECT count(*) FROM "{t}" WHERE {ins("id", list(ids))} AND company_id<>\'{C}\''))
                if count:
                    blockers.add(f'Outside-company records: {t}')
        print(json.dumps({'database': await c.scalar(text('select current_database()')),
                          'candidate_counts': {t: len(ids) for t, ids in sorted(selected.items()) if ids},
                          'blockers': sorted(blockers), 'read_only': True,
                          'retail_legacy_import': False, 'central_stock_selected': False}), flush=True)
        records = {}
        for t, ids in selected.items():
            if ids:
                records[t] = [r['row'] for r in await rows(c, f'SELECT to_jsonb(x) row FROM "{t}" x WHERE {ins("id", list(ids))}')]
        await c.rollback()
        assert not blockers, sorted(blockers)
        return dict(cols), fks, records

async def main():
    for eng, kind in [(platform_engine, 'platform'), (engine, 'restaurant'), (retail_engine, 'retail')]:
        await inspect(eng, kind)

if __name__ == '__main__':
    asyncio.run(main())
