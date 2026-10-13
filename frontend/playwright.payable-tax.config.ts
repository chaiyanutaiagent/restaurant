import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", testMatch: "payable-tax.spec.ts", workers: 1, retries: 0,
  timeout: 30_000, reporter: [["line"]], outputDir: "/private/tmp/restaurant-payable-tax-playwright",
  use: { baseURL: "http://127.0.0.1:4197", channel: "chrome", screenshot: "only-on-failure" },
  webServer: { command: "npm run dev -- --host 127.0.0.1 --port 4197 --strictPort",
    url: "http://127.0.0.1:4197", reuseExistingServer: false, env: { CI_DISABLE_PWA: "true" } }
});
