"""Run payment readiness checks in an isolated, network-disabled release container."""
import os
import unittest

os.environ.update({
    'POSTGRES_DB': 'test', 'POSTGRES_USER': 'test', 'POSTGRES_PASSWORD': 'test',
    'POSTGRES_HOST': '127.0.0.1', 'POSTGRES_PORT': '5432',
    'DATABASE_URL': 'postgresql+asyncpg://test:test@127.0.0.1:5432/test',
    'REDIS_URL': 'redis://127.0.0.1:6379/0',
    'SECRET_KEY': 'test-only-not-a-real-secret-1234567890',
    'ALGORITHM': 'HS256', 'ACCESS_TOKEN_EXPIRE_MINUTES': '15', 'REFRESH_TOKEN_EXPIRE_DAYS': '7',
    'ENVIRONMENT': 'test', 'CORS_ORIGINS': '[]', 'APP_NAME': 'test', 'APP_VERSION': 'test',
    'CELERY_BROKER_URL': 'redis://127.0.0.1:6379/1',
    'CELERY_RESULT_BACKEND': 'redis://127.0.0.1:6379/2',
})
suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_retail_manual_payment_release')
raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
