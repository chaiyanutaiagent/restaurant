"""Self-contained, network-disabled container unit-test entry point."""
if __name__ == '__main__':
    import os
    import unittest
    settings = {
        'POSTGRES_DB':'test', 'POSTGRES_USER':'test', 'POSTGRES_PASSWORD':'test',
        'POSTGRES_HOST':'127.0.0.1', 'POSTGRES_PORT':'5432',
        'DATABASE_URL':'postgresql+asyncpg://test:test@127.0.0.1:5432/test',
        'REDIS_URL':'redis://127.0.0.1:6379/0', 'SECRET_KEY':'test-only-not-a-real-secret-1234567890',
        'ALGORITHM':'HS256', 'ACCESS_TOKEN_EXPIRE_MINUTES':'15', 'REFRESH_TOKEN_EXPIRE_DAYS':'7',
        'ENVIRONMENT':'test', 'CORS_ORIGINS':'[]', 'APP_NAME':'test', 'APP_VERSION':'test',
        'CELERY_BROKER_URL':'redis://127.0.0.1:6379/1', 'CELERY_RESULT_BACKEND':'redis://127.0.0.1:6379/2',
    }
    os.environ.update(settings)
    suite = unittest.defaultTestLoader.loadTestsFromNames(['tests.test_retail_intake','tests.test_retail_catalog_images'])
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
