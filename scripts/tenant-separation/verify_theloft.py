"""Read-only tenant/context checks. Rehearsal prefix selects isolated databases."""
import asyncio, os, uuid, json
from sqlalchemy.engine import make_url
from sqlalchemy import select, text
from app.config import settings
prefix=os.environ.get('THELOFT_REHEARSAL_PREFIX')
if prefix:
    assert prefix=='theloft_rehearsal_20261025'
    for field,kind in [('database_url','restaurant'),('platform_database_url','platform'),
                       ('restaurant_database_url','restaurant'),('retail_database_url','retail')]:
        value=getattr(settings,field) or settings.database_url
        setattr(settings,field,make_url(value).set(database=prefix+'_'+kind).render_as_string(hide_password=False))
from app.database import PlatformSessionLocal, AsyncSessionLocal, RetailSessionLocal
from app.models.user import User
from app.services.auth_service import AuthService
from fastapi import HTTPException
NEW='9b766136-c10f-4ef4-856f-b2f95b943f5e'
OLD='1b8a1818-44d6-4d5f-9d22-e5e17b23c081'
async def main():
    report={}
    async with PlatformSessionLocal() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        for name, branch, kind in [('pam.admin','0b605c63-2d2c-5775-9561-e741c65286f7','restaurant'),
                                   ('loft.admin','cc8e47e0-6e02-5783-8401-180c5061717c','retail')]:
            user=await db.scalar(select(User).where(User.username==name,User.company_id==uuid.UUID(NEW)))
            assert user and user.is_active and not user.is_superuser
            svc=AuthService(db)
            permissions,selected,context,station,assignments,scopes=await svc.get_user_permissions(user,None)
            assert str(selected)==branch and str(context.company_id)==NEW
            assert permissions and assignments and 'branch' in scopes
            oldhash=await db.scalar(text('SELECT hashed_password FROM uat_theloft_separation_20261025.users WHERE id=:id'),{'id':user.id})
            assert oldhash==user.hashed_password
            try:
                await svc.get_user_permissions(user,uuid.UUID('1f397253-0479-4970-8288-f72d6cde6d7e'))
            except HTTPException as e:
                assert e.status_code in [403,404]
            else:
                raise AssertionError('Chambo access should be rejected')
            report[name]={'company':str(context.company_id),'branch':str(selected),'business_type':context.business_type,
                          'permission_count':len(permissions),'password_preserved':True,'chambo_denied':True}
        company=(await db.execute(text('SELECT name,tax_id,name_en,vat_registered FROM companies WHERE id=:id'),{'id':uuid.UUID(NEW)})).mappings().one()
        assert not company['tax_id'] and not company['vat_registered']
        assert await db.scalar(text('SELECT count(*) FROM branches WHERE company_id=:id AND is_active'),{'id':uuid.UUID(NEW)})==3
        assert await db.scalar(text("SELECT count(*) FROM users WHERE company_id=:id AND username='superadmin' AND is_active"),{'id':uuid.UUID(OLD)})==1
        assert await db.scalar(text("SELECT count(*) FROM branches WHERE id='1f397253-0479-4970-8288-f72d6cde6d7e' AND company_id=:id AND is_active"),{'id':uuid.UUID(OLD)})==1
        report['company']=dict(company)
    async with RetailSessionLocal() as db:
        await db.execute(text('SET TRANSACTION READ ONLY'))
        for t in ['products','sale_orders','stock_balances','stock_movements','cashier_shifts']:
            assert await db.scalar(text(f'SELECT count(*) FROM {t} WHERE company_id=:id'),{'id':uuid.UUID(NEW)})==0
        report['retail_empty']=True
    print(json.dumps(report,ensure_ascii=False,default=str))
asyncio.run(main())
