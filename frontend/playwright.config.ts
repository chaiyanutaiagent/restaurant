import { defineConfig } from "@playwright/test";

const artifactDir = process.env.P5_READINESS_ARTIFACT_DIR ?? "/private/tmp/restaurant-p5-playwright";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 20_000 },
  outputDir: `${artifactDir}/test-results`,
  reporter: [
    ["line"],
    ["json", { outputFile: `${artifactDir}/playwright-report.json` }],
  ],
  use: {
    baseURL: process.env.P5_UAT_BASE_URL ?? "http://127.0.0.1:18081",
    serviceWorkers: "block",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
});
