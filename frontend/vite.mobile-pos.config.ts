import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  if (mode !== "pos-uat") throw new Error("POS native builds are UAT only; Production remains on HOLD");
  return {
    // Do not load tenant IDs, auto-login, credentials or legacy updater settings
    // from developer .env files into a distributable app.
    envDir: path.resolve(__dirname, "node_modules/.pos-isolated-env"),
    envPrefix: [] as string[],
    define: {
      "import.meta.env.VITE_APP_SURFACE": JSON.stringify("pos-uat"),
      "import.meta.env.VITE_API_BASE_URL": JSON.stringify("https://uat-restaurant.foodchainservice.com"),
      "import.meta.env.VITE_PUBLIC_APP_ORIGIN": JSON.stringify("https://uat-takeaway.foodchainservice.com"),
      "import.meta.env.VITE_UAT_AUTO_LOGIN": JSON.stringify("false"),
    },
    cacheDir: "node_modules/.vite-mobile-pos",
    optimizeDeps: { entries: ["src/mobile-pos/main.tsx"] },
    plugins: [react(), {
      name: "native-pos-adapters",
      enforce: "pre" as const,
      resolveId(source: string, importer?: string) {
        if (!importer) return null;
        const base = importer.split("?")[0];
        if (base.includes("/src/lib/") && source === "./api") return path.resolve(__dirname, "src/mobile-pos/api.ts");
        if (base.includes("/src/mobile-store/") && ["./session", "./api", "./db"].includes(source)) {
          return path.resolve(__dirname, `src/mobile-pos/${source === "./db" ? "storeDb" : source.slice(2)}.ts`);
        }
        return null;
      },
    }, {
      name: "pos-only-entry",
      transformIndexHtml: { order: "pre", handler: (html: string) => html
        .replace("/src/main.tsx", "/src/mobile-pos/main.tsx")
        .replace('initial-scale=1.0', 'initial-scale=1.0, viewport-fit=cover') },
    }],
    resolve: { alias: [
      { find: "@/stores/auth.store", replacement: path.resolve(__dirname, "src/mobile-pos/session.ts") },
      { find: "@/lib/api", replacement: path.resolve(__dirname, "src/mobile-pos/api.ts") },
      { find: "@/hooks/useAuth", replacement: path.resolve(__dirname, "src/mobile-pos/useAuth.ts") },
      { find: "@/lib/takeawayApi", replacement: path.resolve(__dirname, "src/mobile-store/takeawayApi.ts") },
      { find: "@", replacement: path.resolve(__dirname, "src") },
    ] },
    build: { outDir: "dist-mobile-pos", sourcemap: false },
    server: { host: "127.0.0.1", port: 3012, strictPort: true },
  };
});
