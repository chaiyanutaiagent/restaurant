import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e", testMatch: "retail-counter.spec.ts", workers: 1, retries: 0,
  timeout: 45000, reporter: [["line"]], outputDir: "/private/tmp/restaurant-retail-counter-tests",
  use: { baseURL: "http://127.0.0.1:4189", channel: "chrome", screenshot: "only-on-failure" },
  webServer: { command: "npm run dev -- --host 127.0.0.1 --port 4189", url: "http://127.0.0.1:4189", reuseExistingServer: false },
});
