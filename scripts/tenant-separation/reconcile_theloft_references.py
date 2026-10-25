"""Reconcile canonical Retail references after split; no business data copied."""
import asyncio,uuid,json
from sqlalchemy import text
from app.database import RetailSessionLocal
from app.services.retail_reference_projector import project_retail_reference_snapshot,validate_retail_reference_readiness
async def main():
    async with RetailSessionLocal() as db:
        for table in ['companies','branches','brands','brand_branches','users','retail_reference_projection_receipts']:
            await db.execute(text(f'CREATE TABLE IF NOT EXISTS uat_theloft_separation_20261025."before_projection_{table}" AS SELECT * FROM public."{table}"'))
        await db.commit()
    for company in ['1b8a1818-44d6-4d5f-9d22-e5e17b23c081','9b766136-c10f-4ef4-856f-b2f95b943f5e']:
        result=await project_retail_reference_snapshot(company_id=uuid.UUID(company))
        print(json.dumps({'company':company,'scanned':result.scanned,'applied':result.applied,'unchanged':result.unchanged}),flush=True)
    await validate_retail_reference_readiness()
    print('Retail canonical reference parity PASS')
asyncio.run(main())
