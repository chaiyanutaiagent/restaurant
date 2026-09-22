import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "company-distribution.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: "/private/tmp/restaurant-company-distribution-playwright",
  reporter: [["line"]],
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "tablet", use: { viewport: { width: 1024, height: 768 }, hasTouch: true } },
  ],
  use: { baseURL: "http://127.0.0.1:4176", channel: "chrome", serviceWorkers: "block", screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: { command: "npm run dev -- --host 127.0.0.1 --port 4176", url: "http://127.0.0.1:4176/login", reuseExistingServer: true, timeout: 120_000 },
});
