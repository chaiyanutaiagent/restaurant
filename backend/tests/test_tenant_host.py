from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.tenant_host import COMPANY_ID, HOST, TenantHostMiddleware
from app.utils.security import create_access_token, create_refresh_token


class TenantHostTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_middleware(TenantHostMiddleware)

        @app.api_route('/{path:path}', methods=['GET', 'POST'])
        async def echo(request: Request, path: str):
            # Verify reading JSON in middleware doesn't consume the login body.
            return await request.json() if request.method == 'POST' else {'ok': True}

        self.client = TestClient(app, base_url=f'https://{HOST}')
        self.config = patch('app.middleware.tenant_host.settings', SimpleNamespace(
            environment='development', saas_public_base_url='https://uat-app.foodchainservice.com'))
        self.config.start()
        self.addCleanup(self.config.stop)

    def token(self, company=COMPANY_ID, **kwargs):
        return create_access_token('test-user', company, None, [], **kwargs)

    def test_login_body_passes_intact_only_for_bound_company(self):
        body = {'company_id': COMPANY_ID, 'username': 'tester', 'password': 'fixture'}
        response = self.client.post('/api/v1/auth/login', json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), body)
        self.assertEqual(self.client.post('/api/v1/auth/login', json={**body, 'company_id': 'other'}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/auth/login', json=body, headers={'X-Company-ID': 'other'}).status_code, 403)

    def test_access_and_refresh_require_verified_company_token(self):
        url = '/api/v1/company/overview'
        self.assertEqual(self.client.get(url).status_code, 401)
        for token, expected in [(self.token(), 200), (self.token('other'), 403),
                                (self.token(qa_persona='owner'), 403), ('forged', 401)]:
            self.assertEqual(self.client.get(url, headers={'Authorization': f'Bearer {token}'}).status_code, expected)
        for company, expected in [(COMPANY_ID, 200), ('other', 403)]:
            token = create_refresh_token('test-user', company)
            self.assertEqual(self.client.post('/api/v1/auth/refresh', json={'refresh_token': token}).status_code, expected)
        self.assertEqual(self.client.post('/api/v1/auth/refresh', json={'refresh_token': self.token()}).status_code, 403)

    def test_platform_and_bypass_remain_unavailable(self):
        for path in ['/api/v1/platform/login', '/api/v1/auth/uat/auto-login', '/api/v1/auth/qa/session']:
            self.assertEqual(self.client.post(path, json={}).status_code, 404)

    def test_public_bootstrap_and_other_hosts_unchanged(self):
        self.assertEqual(self.client.get('/api/v1/membership/businesses/sketch-biz').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/membership/businesses/other').status_code, 401)
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/company/overview', headers={'Host': 'uat-app.foodchainservice.com'}).status_code, 200)

    def test_alias_fails_closed_outside_uat(self):
        with patch('app.middleware.tenant_host.settings', SimpleNamespace(environment='production', saas_public_base_url='https://app.foodchainservice.com')):
            self.assertEqual(self.client.get('/health').status_code, 404)

    def test_invalid_json_is_rejected(self):
        self.assertEqual(self.client.post('/api/v1/auth/login', content='{').status_code, 400)
