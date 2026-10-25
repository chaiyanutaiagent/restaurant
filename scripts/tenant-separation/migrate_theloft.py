"""Bounded The Loft tenant split. Dry-run rolls back; rehearsal DBs supported.

Clone shared catalog/reference definitions; MOVE mutable store documents and
active staff. Copy immutable events without changing originals. Retire original
storefront routes, retaining the original central kitchen and all stock rows.
No Retail products, sales, stock, or legacy Retail records are imported.
"""
import asyncio
import copy
import json
import os
import uuid
from datetime import datetime, timezone
from collections import defaultdict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.database import engine, platform_engine, retail_engine
from app.config import settings
from theloft_store_graph import inspect, rows, ins, C, B, BR, U

NEW = '9b766136-c10f-4ef4-856f-b2f95b943f5e'
NS = uuid.UUID(NEW)
ARCH = 'uat_theloft_separation_20261025'
MOVE = {'cashier_shifts', 'dining_tables', 'dining_sessions', 'dining_orders', 'dining_order_items',
        'kitchen_tickets', 'employees', 'payroll_runs', 'payroll_items', 'pos_hold_drafts',
        'user_branches', 'staff_role_assignments', 'kitchen_cancellation_events'}
NOW = datetime.now(timezone.utc).isoformat()
SOURCE_ACTOR = '8b45ab10-41ca-4aed-8e90-662f39392996'

def moved(t, old):
    return t in MOVE or (t == 'users' and old in U)

def newid(t, old):
    return old if moved(t, old) else str(uuid.uuid5(NS, t + ':' + old))

async def digest(c, t, pred='true'):
    return await c.scalar(text(f'''SELECT md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM
        (SELECT md5(to_jsonb(x)::text) h FROM public."{t}" x WHERE {pred}) s'''))

async def insert(c, t, record):
    names = ','.join('"'+k+'"' for k in record)
    await c.execute(text(f'INSERT INTO public."{t}" ({names}) SELECT {names} FROM jsonb_populate_record(NULL::public."{t}",CAST(:j AS jsonb))'), {'j': json.dumps(record)})

async def replace(c, t, record):
    names = [k for k in record if k != 'id']
    setters = ','.join('"'+k+'"=r."'+k+'"' for k in names)
    result = await c.execute(text(f'UPDATE public."{t}" x SET {setters} FROM jsonb_populate_record(NULL::public."{t}",CAST(:j AS jsonb)) r WHERE x.id=r.id'), {'j': json.dumps(record)})
    assert result.rowcount == 1, t

def remap(value, mapping):
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [remap(x, mapping) for x in value]
    if isinstance(value, dict):
        return {k: remap(v, mapping) for k, v in value.items()}
    return value

async def main():
    assert settings.environment == 'development' and settings.identity_database == 'platform_core'
    prefix = os.environ.get('THELOFT_REHEARSAL_PREFIX')
    apply = os.environ.get('THELOFT_MIGRATION_APPLY') == 'YES'
    if apply and not prefix:
        assert os.environ.get('THELOFT_MIGRATION_BACKUP_VERIFIED') == 'YES'
        assert os.environ.get('THELOFT_MAINTENANCE_CONFIRMED') == 'YES'
    engines = {'platform': platform_engine, 'restaurant': engine, 'retail': retail_engine}
    if prefix:
        assert prefix == 'theloft_rehearsal_20261025'
        engines = {k: create_async_engine(e.url.set(database=prefix+'_'+k)) for k,e in engines.items()}
    for eng in engines.values():
        eng.sync_engine.hide_parameters = True
    plans = {k: await inspect(e, k) for k,e in engines.items()}
    # Canonical identity and role definitions must exist in each operational DB.
    platform_records = plans['platform'][2]
    for kind in ['restaurant', 'retail']:
        cols, fks, data = plans[kind]
        for t in ['users', 'roles', 'user_branches', 'staff_role_assignments']:
            if t not in cols:
                continue
            own = {r['id']: r for r in data.get(t, [])}
            for r in platform_records.get(t, []):
                if t in ['user_branches', 'staff_role_assignments']:
                    if r.get('branch_id') not in (B[:2] if kind=='restaurant' else B[2:]):
                        continue
                own[r['id']] = {x:v for x,v in r.items() if x in cols[t]}
            data[t] = list(own.values())
    mapping = {C: NEW}
    for _,_,data in plans.values():
        for t, records in data.items():
            for r in records:
                mapping[r['id']] = newid(t, r['id'])
    # Cross-DB brand/location mappings must be identical, including Platform
    # references that lack stock-location columns in their schema.
    for old in B:
        mapping[old] = newid('branches', old)
    for old in BR:
        mapping[old] = newid('brands', old)
    connections = {}; transactions = {}; summaries = {}
    try:
        for kind, eng in engines.items():
            c = await eng.connect(); connections[kind] = c
            transactions[kind] = await c.begin()
            cols, fks, data = plans[kind]
            assert not await c.scalar(text(f"SELECT count(*) FROM companies WHERE id='{NEW}' OR business_slug='theloft'")), 'The Loft already exists'
            assert not await c.scalar(text(f"SELECT count(*) FROM pg_namespace WHERE nspname='{ARCH}'")), 'Already migrated'
            await c.execute(text("SET LOCAL lock_timeout='8s'"))
            await c.execute(text(f'CREATE SCHEMA "{ARCH}"'))
            # A complete row-level preimage supports scoped compensation. Never
            # overwrite a whole production/UAT database to roll back this split.
            modified = {}
            for t, recs in data.items():
                move_ids = [r['id'] for r in recs if moved(t, r['id'])]
                if move_ids:
                    modified[t] = ins('id', move_ids)
            for t, cond in {
                'brands': ins('id', BR), 'branches': ins('id', B),
                'brand_branches': ins('brand_id', BR),
                'branch_settings': ins('branch_id', B),
                'device_registrations': ins('branch_id', B),
                'refresh_tokens': ins('user_id', U),
                'saas_account_credentials': ins('owner_user_id', U),
                'user_invitations': ins('branch_id', B),
            }.items():
                if t in cols:
                    modified[t] = '('+modified[t]+') OR ('+cond+')' if t in modified else cond
            before = {t: await digest(c,t,'NOT ('+modified[t]+')' if t in modified else 'true') for t in cols}
            originals = {}
            for t, pred in modified.items():
                await c.execute(text(f'CREATE TABLE "{ARCH}"."{t}" AS SELECT * FROM public."{t}" WHERE {pred}'))
                originals[t] = await c.scalar(text(f'SELECT count(*) FROM "{ARCH}"."{t}"'))
            await c.execute(text('''INSERT INTO companies (id,name,business_slug,name_en,currency,timezone,vat_registered,is_active,credential_version)
                VALUES (:id,'The Loft','theloft','The Loft','THB','Asia/Bangkok',false,true,1)'''), {'id': uuid.UUID(NEW)})
            transformed = {}; pending = {}; changed = defaultdict(list)
            for t, recs in data.items():
                for old in recs:
                    r = remap(copy.deepcopy(old), mapping)
                    if 'company_id' in r: r['company_id'] = NEW
                    if t == 'users':
                        r['is_superuser'] = False
                        if old['id'] in U:
                            if 'credential_version' in cols[t]:
                                r['credential_version'] = old.get('credential_version',1)+1
                            assert old['is_active'] and not old.get('deleted_at')
                        else:
                            r['is_active'] = False
                            r['username'] = 'history.'+old['username'][:85]
                            r['email'] = None
                    if t == 'brands' and old['id'] == BR[1]:
                        r['name'] = 'Loft Restaurant'
                    if t == 'branches' and old['id'] == B[1]:
                        r['name'] = 'Loft Restaurant สาขาไทรน้อย'
                    if t == 'branch_settings':
                        for field in ['promptpay_target','promptpay_name','promptpay_qr_url','fb_line_notify_token']:
                            if field in r: r[field] = None
                        if 'receipt_show_tax_id' in r: r['receipt_show_tax_id'] = False
                        if 'fb_qs_qr_token' in r: r['fb_qs_qr_token'] = None
                    if t == 'stock_locations':
                        # A location definition is copied; source quantities stay
                        # with central/test stock at Sketch Biz. No balances copied.
                        assert old['branch_id'] in B
                    transformed[t,old['id']] = r
                    if not moved(t,old['id']): pending[t,old['id']] = r
            # Parent-first insertion; existing MOVE rows retain IDs. FK cycles
            # and unreviewed dependencies fail instead of disabling constraints.
            inserted = set()
            while pending:
                progress = False
                for key,r in list(pending.items()):
                    t,oldid = key
                    deps = []
                    for f in fks:
                        if f['child'] != t or r.get(f['col']) is None: continue
                        dep = next((pkey for pkey,pr in pending.items() if pkey[0]==f['parent'] and pr.get(f['parent_col'])==r[f['col']]), None)
                        if dep: deps.append(dep)
                    if deps: continue
                    await insert(c,t,r); inserted.add(key); del pending[key]
                    changed[t].append(r.get('id')); progress = True
                assert progress, 'Insertion cycle: '+str(list(pending))
            for (t,oldid),r in transformed.items():
                if moved(t,oldid):
                    if await c.scalar(text(f'SELECT count(*) FROM "{t}" WHERE id=:id'), {'id':uuid.UUID(oldid)}):
                        await replace(c,t,r)
                    else:
                        await insert(c,t,r)
                    changed[t].append(r['id'])
            # Same permission IDs are global reference data, never duplicated.
            if data.get('roles'):
                async with engines['platform'].connect() as source:
                    perms = await rows(source, 'SELECT rp.*,to_jsonb(p) definition FROM role_permissions rp JOIN permissions p ON p.id=rp.permission_id WHERE '+ins('role_id',[r['id'] for r in data['roles']]))
                for p in perms:
                    definition = p['definition']
                    permission_id = await c.scalar(text('SELECT id FROM permissions WHERE code=:code'), {'code':definition['code']})
                    if permission_id is None:
                        await insert(c,'permissions',definition)
                        changed['permissions'].append(definition['id'])
                        permission_id = uuid.UUID(definition['id'])
                    await c.execute(text('INSERT INTO role_permissions (role_id,permission_id,created_at) VALUES (:r,:p,:at)'),
                                    {'r':uuid.UUID(newid('roles',str(p['role_id']))), 'p':permission_id, 'at':p['created_at']})
            # Retire ONLY storefront navigation. KPP source remains the central
            # kitchen's warehouse; don't relabel/mutate its stock or recipes.
            # KPP's original branch is also the Restaurant central kitchen.
            # Keep its business context usable; only its storefront is disabled.
            await c.execute(text(f"UPDATE brand_branches SET is_active=false WHERE {ins('brand_id',BR[1:])}"))
            await c.execute(text(f"UPDATE brands SET is_active=false WHERE {ins('id',BR[1:])}"))
            await c.execute(text(f"UPDATE branches SET is_active=false WHERE {ins('id',B[1:])}"))
            await c.execute(text(f"UPDATE branches SET name='ครัวกลาง Restaurant · Sketch Biz',is_warehouse=true WHERE id='{B[0]}'"))
            await c.execute(text(f"UPDATE brands SET name='ครัวกลาง Restaurant · Sketch Biz' WHERE id='{BR[0]}'"))
            if 'branch_settings' in cols:
                await c.execute(text(f"UPDATE branch_settings SET public_storefront_enabled=false WHERE {ins('branch_id',B)}"))
            if 'device_registrations' in cols:
                await c.execute(text(f"""UPDATE device_registrations SET revoked_at=coalesce(revoked_at,now()),
                    revocation_reason=coalesce(revocation_reason,'The Loft tenant split: pair device again'),
                    credential_version=credential_version+1,pairing_pin_hash=null,pairing_expires_at=null,
                    refresh_credential_hash=null,refresh_credential_issued_at=null
                    WHERE {ins('branch_id',B)} AND revoked_at IS NULL"""))
            if 'refresh_tokens' in cols:
                await c.execute(text(f"UPDATE refresh_tokens SET revoked_at=now() WHERE {ins('user_id',U)} AND revoked_at IS NULL"))
            if 'saas_account_credentials' in cols:
                await c.execute(text(f"UPDATE saas_account_credentials SET company_id='{NEW}' WHERE {ins('owner_user_id',U)}"))
            if 'user_invitations' in cols:
                await c.execute(text(f"UPDATE user_invitations SET revoked_at=now() WHERE {ins('branch_id',B)} AND used_at IS NULL AND revoked_at IS NULL"))
            if kind == 'platform':
                source_profile = (await rows(c, f"SELECT to_jsonb(p) row FROM platform_tenant_profiles p WHERE company_id='{C}'"))[0]['row']
                source_profile.update(id=str(uuid.uuid5(NS,'profile')), company_id=NEW, created_at=NOW, updated_at=NOW)
                source_profile['feature_flags'] = {**source_profile['feature_flags'], 'restaurant': True, 'restaurant_pos': True, 'retail_pos': True, 'takeaway': False, 'takeaway_pos': False, 'central_kitchen': False}
                await insert(c,'platform_tenant_profiles',source_profile)
                changed['platform_tenant_profiles'].append(source_profile['id'])
                entitlements = await rows(c, 'SELECT to_jsonb(e) row FROM brand_module_entitlements e WHERE '+ins('brand_id',BR))
                for entry in entitlements:
                    old = entry['row']; r = remap(old,mapping)
                    r['id'] = str(uuid.uuid5(NS,'entitlement:'+old['id']))
                    if r['module_key'] in ['takeaway','takeaway_pos','central_kitchen']: r['is_enabled'] = False
                    await insert(c,'brand_module_entitlements',r)
                    changed['brand_module_entitlements'].append(r['id'])
            # Preserve all original rows outside the explicit preimages. Newly
            # inserted clones are excluded by their IDs only, never by company.
            for t, oldhash in before.items():
                predicate = 'NOT ('+modified[t]+')' if t in modified else 'true'
                extra = [x for x in changed[t] if x]
                if t == 'companies': extra.append(NEW)
                if extra: predicate += ' AND NOT ('+ins('id',extra)+')'
                if t == 'role_permissions' and data.get('roles'):
                    predicate += ' AND NOT ('+ins('role_id',[newid('roles',r['id']) for r in data['roles']])+')'
                assert oldhash == await digest(c,t,predicate), 'Protected data changed: '+kind+'.'+t
            # New reference rows must never point into another tenant, except
            # global Platform operator/permission identifiers and immutable
            # original history which this script never edits.
            for t, recs in data.items():
                for old in recs:
                    r = transformed[t,old['id']]
                    for f in fks:
                        if f['child'] != t or not r.get(f['col']) or 'company_id' not in cols.get(f['parent'],set()): continue
                        pc = await c.scalar(text(f'SELECT company_id::text FROM "{f["parent"]}" WHERE "{f["parent_col"]}"::text=:v'), {'v':str(r[f['col']])})
                        assert pc == NEW, f'Cross-tenant new reference {kind}:{t}.{f["col"]}->{f["parent"]}'
            if kind == 'retail':
                for t in ['products','sale_orders','stock_balances','stock_movements','cashier_shifts']:
                    assert not await c.scalar(text(f"SELECT count(*) FROM {t} WHERE company_id='{NEW}'")), t
            summaries[kind] = {'records': {t:len(r) for t,r in data.items()}, 'protected_tables':len(before), 'retail_empty':kind=='retail'}
            await c.execute(text(f'CREATE TABLE "{ARCH}".migration_manifest (payload jsonb NOT NULL)'))
            await c.execute(text(f'INSERT INTO "{ARCH}".migration_manifest VALUES (CAST(:j AS jsonb))'),
                            {'j':json.dumps({'company':NEW,'kind':kind,'modified_tables':list(modified),
                                             'changed':dict(changed),'summary':summaries[kind]})})
        # Operational DBs first; identity last. If a commit fails, keep identity
        # closed and use archived row preimages for scoped compensation.
        for kind in ['restaurant','retail','platform']:
            if apply:
                await transactions[kind].commit(); print('COMMITTED '+kind,flush=True)
            else:
                await transactions[kind].rollback()
        print(json.dumps({'result':'APPLIED' if apply else 'REHEARSED_ROLLBACK','rehearsal_prefix':prefix,
                          'new_company':NEW,'branch_map':{x:mapping[x] for x in B},'brand_map':{x:mapping[x] for x in BR},
                          'summary':summaries}),flush=True)
    finally:
        for tx in transactions.values():
            if tx.is_active: await tx.rollback()
        for c in connections.values(): await c.close()
        if prefix:
            for eng in engines.values(): await eng.dispose()

if __name__ == '__main__':
    asyncio.run(main())
