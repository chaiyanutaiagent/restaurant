import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), ""), ...process.env };
  if (mode !== "android-uat" || env.VITE_UAT_AUTO_LOGIN !== "false"
      || env.VITE_COMPANY_ID || env.VITE_BUSINESS_SLUG
      || env.VITE_API_BASE_URL !== "https://uat-takeaway.foodchainservice.com") {
    throw new Error("Store candidate requires UAT HTTPS, auto-login=false, and no default tenant");
  }
  return {
    cacheDir: "node_modules/.vite-mobile-store",
    optimizeDeps: { entries: ["src/mobile-store/main.tsx"] },
    plugins: [react(), {
      name: "store-only-entry",
      transformIndexHtml: { order: "pre", handler: (html: string) => html.replace("/src/main.tsx", "/src/mobile-store/main.tsx") },
    }],
    resolve: { alias: [
      { find: "@/stores/auth.store", replacement: path.resolve(__dirname, "src/mobile-store/session.ts") },
      { find: "@/lib/takeawayApi", replacement: path.resolve(__dirname, "src/mobile-store/takeawayApi.ts") },
      { find: "@/lib/db", replacement: path.resolve(__dirname, "src/mobile-store/db.ts") },
      { find: "@/lib/takeawayAppUpdate", replacement: path.resolve(__dirname, "src/mobile-store/appUpdate.ts") },
      { find: "@", replacement: path.resolve(__dirname, "src") },
    ] },
    build: { outDir: "dist-mobile-store", sourcemap: false },
    server: { host: "127.0.0.1", port: 3011 },
  };
});
