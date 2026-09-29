import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e", testMatch: "mobile-store.spec.ts", workers: 1, retries: 0,
  timeout: 30000, reporter: [["line"]], outputDir: "/private/tmp/foodchainservice-store-playwright",
  use: { baseURL: "http://127.0.0.1:3011", channel: "chrome", viewport: { width: 1024, height: 768 }, trace: "retain-on-failure" },
  webServer: { command: "npx vite --config vite.mobile-store.config.ts --mode android-uat --host 127.0.0.1 --port 3011", url: "http://127.0.0.1:3011", reuseExistingServer: false },
});
