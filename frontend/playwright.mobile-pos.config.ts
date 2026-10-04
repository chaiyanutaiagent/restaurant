import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", testMatch: "mobile-pos.spec.ts", workers: 1, retries: 0,
  timeout: 30000, reporter: [["line"]], outputDir: "test-results/mobile-pos",
  use: { baseURL: "http://127.0.0.1:3012", channel: "chrome", viewport: { width: 1024, height: 768 }, trace: "retain-on-failure" },
  webServer: { command: "npm run dev:pos", url: "http://127.0.0.1:3012", reuseExistingServer: false },
});
