"""Maintenance-only compensation. Restores archived rows, keeps immutable clones.

Does not delete new history or restore whole databases. Run only before reopening
UAT (or after reviewing all subsequent writes). Retains revoked sessions/devices.
The new tenant is made inactive; immutable copies remain inaccessible history.
"""
import asyncio,os,uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.database import engine,platform_engine,retail_engine
from migrate_theloft import ARCH,NEW,replace
async def main():
    prefix=os.environ.get('THELOFT_REHEARSAL_PREFIX')
    assert prefix=='theloft_rehearsal_20261025' or os.environ.get('THELOFT_ROLLBACK_MAINTENANCE')=='YES'
    engines={'platform':platform_engine,'restaurant':engine,'retail':retail_engine}
    if prefix: engines={k:create_async_engine(e.url.set(database=prefix+'_'+k)) for k,e in engines.items()}
    for kind in ['platform','restaurant','retail']:
        async with engines[kind].begin() as c:
            exists=await c.scalar(text('SELECT count(*) FROM pg_namespace WHERE nspname=:s'),{'s':ARCH})
            if not exists: continue
            manifest=await c.scalar(text(f'SELECT payload FROM "{ARCH}".migration_manifest'))
            for table in manifest['modified_tables']:
                if table in ['refresh_tokens','device_registrations','user_invitations']: continue
                records=(await c.execute(text(f'SELECT to_jsonb(x) FROM "{ARCH}"."{table}" x'))).scalars().all()
                for record in records: await replace(c,table,record)
            await c.execute(text('UPDATE companies SET is_active=false,credential_version=credential_version+1 WHERE id=:id'),{'id':uuid.UUID(NEW)})
            await c.execute(text('UPDATE users SET is_active=false WHERE company_id=:id'),{'id':uuid.UUID(NEW)})
            await c.execute(text('UPDATE branches SET is_active=false WHERE company_id=:id'),{'id':uuid.UUID(NEW)})
            print('COMPENSATED '+kind,flush=True)
    if prefix:
        for e in engines.values(): await e.dispose()
asyncio.run(main())
