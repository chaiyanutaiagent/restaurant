"""Authenticated GET-only smoke checks; tokens never leave process or print.
Uses actual current branch permissions, not wildcard or QA access. No login,
password change, refresh session, sale, or stock transaction is created.
"""
import asyncio,json,uuid
from datetime import timedelta
import httpx
from sqlalchemy import select
from app.database import PlatformSessionLocal
from app.models.user import User
from app.models.company import Company
from app.services.auth_service import AuthService
from app.utils.security import create_access_token
NEW=uuid.UUID('9b766136-c10f-4ef4-856f-b2f95b943f5e')
async def main():
    report={}
    async with PlatformSessionLocal() as db,httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=30) as client:
        company=await db.get(Company,NEW)
        for name,scope in [('pam.admin','restaurant_menu'),('loft.admin','retail_sale')]:
            user=await db.scalar(select(User).where(User.company_id==NEW,User.username==name))
            perms,branch,context,station,assignments,scopes=await AuthService(db).get_user_permissions(user,None)
            token=create_access_token(str(user.id),str(NEW),str(branch),perms,timedelta(minutes=2),
                brand_id=str(context.brand_id),business_type=context.business_type,target_database=context.target_database,
                station_key=station,assignment_ids=[str(a) for a in assignments],scope_types=scopes,
                company_credential_version=company.credential_version,user_credential_version=user.credential_version)
            headers={'Host':'theloft.foodchainservice.com','Authorization':'Bearer '+token}
            paths=['/api/v1/auth/me','/api/v1/company/context',
                   '/api/v1/products?catalog_scope='+scope]
            if name=='pam.admin':paths.extend(['/api/v1/restaurant/tables','/api/v1/restaurant/me/brand-navigation'])
            results={}
            for path in paths:
                r=await client.get(path,headers=headers)
                if r.status_code!=200:
                    print(json.dumps({'user':name,'path':path,'status':r.status_code,'error':r.text[:500]}),flush=True)
                assert r.status_code==200,(name,path,r.status_code)
                results[path]=r.status_code
            r=await client.get('/api/v1/auth/me',headers={**headers,'Host':'sketchbiz.foodchainservice.com'})
            assert r.status_code==403
            report[name]=results
        for host,slug in [('theloft.foodchainservice.com','theloft'),('sketchbiz.foodchainservice.com','sketch-biz')]:
            r=await client.get('/api/v1/membership/businesses/'+slug,headers={'Host':host})
            assert r.status_code==200,(host,r.status_code)
        r=await client.get('/api/v1/auth/me',headers={'Host':'theloft.foodchainservice.com'})
        assert r.status_code==401
        print(json.dumps({'api_smoke':'PASS','checks':report,'cross_company_denied':True,'anonymous_denied':True}))
asyncio.run(main())
