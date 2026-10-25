import asyncio,json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.database import engine,takeaway_engine
OLD='1b8a1818-44d6-4d5f-9d22-e5e17b23c081'
async def digest(c,t):
    return await c.scalar(text(f"SELECT md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(to_jsonb(x)::text) h FROM {t} x) s"))
async def main():
    reference=create_async_engine(engine.url.set(database='theloft_rehearsal_20261025_restaurant'))
    async with engine.connect() as live,reference.connect() as before:
        for table in ['stock_balances','stock_movements','company_kitchens']:
            assert await digest(live,table)==await digest(before,table),table
        assert await live.scalar(text(f"SELECT count(*) FROM company_kitchens WHERE company_id='{OLD}' AND is_active"))==1
        print('Restaurant central kitchen + ALL stock balances/movements unchanged from pre-migration backup')
    async with takeaway_engine.connect() as c:
        tables=(await c.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('brands','branches','takeaway_recipes','takeaway_stock_balances')"))).scalars().all()
        report={}
        for table in tables:
            report[table]=await c.scalar(text(f"SELECT count(*) FROM {table} WHERE company_id='{OLD}'"))
        print(json.dumps({'Chambo_company_still_Sketch_Biz':report}))
    await reference.dispose()
asyncio.run(main())
