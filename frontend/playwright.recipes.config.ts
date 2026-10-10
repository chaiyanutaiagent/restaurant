import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', testMatch: ['recipe-quick-create.spec.ts', 'company-kitchen.spec.ts'],
  workers: 1, retries: 0, timeout: 45_000, expect: { timeout: 10_000 }, reporter: [['line']],
  outputDir: '/private/tmp/foodchain-recipe-quick-create',
  use: { baseURL: 'http://127.0.0.1:4203', channel: 'chrome', serviceWorkers: 'block', screenshot: 'only-on-failure' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 4203 --strictPort', url: 'http://127.0.0.1:4203/login', reuseExistingServer: false },
});
