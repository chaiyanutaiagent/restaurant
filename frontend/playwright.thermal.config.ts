import { defineConfig } from "@playwright/test";
const port = Number(process.env.THERMAL_E2E_PORT ?? 4201);
export default defineConfig({
  testDir: "./e2e", testMatch: ["thermal-print.spec.ts", "takeaway-workspace.spec.ts", "company-shell.spec.ts"],
  workers: 1, retries: 0, timeout: 60_000, expect: { timeout: 10_000 },
  reporter: [["line"]], outputDir: "/private/tmp/foodchain-thermal-print",
  use: { baseURL: `http://127.0.0.1:${port}`, channel: "chrome", serviceWorkers: "block", screenshot: "only-on-failure" },
  webServer: { command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: `http://127.0.0.1:${port}/login`, reuseExistingServer: false, timeout: 120_000 },
});
