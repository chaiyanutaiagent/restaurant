import { defineConfig } from "@playwright/test";

const artifactDir = process.env.INTEGRATION_E2E_ARTIFACT_DIR ?? "/private/tmp/restaurant-integration-playwright";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "integration-governance.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: `${artifactDir}/test-results`,
  reporter: [["line"]],
  use: { baseURL: "http://127.0.0.1:4176", channel: "chrome", screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: { command: "npm run dev -- --host 127.0.0.1 --port 4176", url: "http://127.0.0.1:4176/integrations", reuseExistingServer: true, timeout: 120_000 },
});
