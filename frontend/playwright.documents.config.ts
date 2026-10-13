import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "company-documents.spec.ts",
  workers: 1,
  retries: 0,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  outputDir: "/private/tmp/restaurant-documents-playwright",
  reporter: [["line"]],
  use: {
    baseURL: "http://127.0.0.1:4196",
    channel: "chrome",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4196 --strictPort",
    url: "http://127.0.0.1:4196/company/documents",
    reuseExistingServer: false,
    timeout: 120_000,
    env: { CI_DISABLE_PWA: "true" },
  },
});
