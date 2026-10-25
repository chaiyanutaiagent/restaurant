"""Add only missing Platform reference rows for legacy Company Shell reads.
No catalog, stock, transactions, or old Retail test records are imported.
"""
import asyncio,uuid,json
from sqlalchemy import text
from app.database import PlatformSessionLocal,AsyncSessionLocal
from app.services.platform_reference_projection import REFERENCE_COLUMNS,REFERENCE_TABLES
NEW=uuid.UUID('9b766136-c10f-4ef4-856f-b2f95b943f5e')
async def main():
    inserted={}
    async with PlatformSessionLocal() as source,AsyncSessionLocal() as target:
        for aggregate in ['branch','brand','brand_branch']:
            table=REFERENCE_TABLES[aggregate]; columns=REFERENCE_COLUMNS[aggregate]
            records=(await source.execute(text(f'SELECT {",".join(columns)} FROM {table} WHERE company_id=:c'),{'c':NEW})).mappings().all()
            for r in records:
                if await target.scalar(text(f'SELECT count(*) FROM {table} WHERE id=:id'),{'id':r['id']}):continue
                values=','.join('CAST(:theme_config AS jsonb)' if x=='theme_config' else ':'+x for x in columns)
                params=dict(r)
                if 'theme_config' in params:params['theme_config']=json.dumps(params['theme_config'])
                await target.execute(text(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({values})'),params)
                inserted.setdefault(table,[]).append(str(r['id']))
        await target.execute(text('CREATE TABLE uat_theloft_separation_20261025.context_reference_manifest (payload jsonb NOT NULL)'))
        await target.execute(text('INSERT INTO uat_theloft_separation_20261025.context_reference_manifest VALUES (CAST(:j AS jsonb))'),{'j':json.dumps(inserted)})
        await target.commit()
    print(json.dumps({'context_references_inserted':inserted}))
asyncio.run(main())
