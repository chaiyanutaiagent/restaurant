import { defineConfig } from "@playwright/test";

const artifactDir = process.env.RETAIL_E2E_ARTIFACT_DIR ?? "/private/tmp/restaurant-retail-playwright";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "retail-workspace.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir: `${artifactDir}/test-results`,
  reporter: [["line"]],
  use: { baseURL: "http://127.0.0.1:4177", channel: "chrome", screenshot: "only-on-failure", trace: "retain-on-failure" },
  webServer: { command: "npm run dev -- --host 127.0.0.1 --port 4177", url: "http://127.0.0.1:4177/retail/pos", reuseExistingServer: true, timeout: 120_000 },
});
