import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const product = process.env.FCS_POS_PRODUCT;
  if (mode !== "native-uat" || !["retail", "restaurant"].includes(product ?? '')) throw new Error('Select retail/restaurant UAT explicitly');
  if (process.env.VITE_UAT_AUTO_LOGIN === 'true' || process.env.VITE_COMPANY_ID || process.env.VITE_BUSINESS_SLUG) throw new Error('Native POS must not embed tenant or auto-login');
  const origin = product === 'retail' ? 'https://uat-retail.foodchainservice.com' : 'https://uat-pos.foodchainservice.com';
  const revision = product === 'retail' ? 14 : 6;
  return {
    // No environment file inheritance from the existing Takeaway or web builds.
    envDir: false,
    define: {
      'import.meta.env.VITE_NATIVE_POS_PRODUCT': JSON.stringify(product),
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(origin),
      'import.meta.env.VITE_UAT_AUTO_LOGIN': JSON.stringify('false'),
      'import.meta.env.VITE_COMPANY_ID': 'undefined',
      'import.meta.env.VITE_BUSINESS_SLUG': 'undefined',
    },
    cacheDir: `node_modules/.vite-native-${product}`,
    optimizeDeps: { entries: ['src/native-pos/main.tsx'] },
    plugins: [react(), {
      name: 'native-pos-entry',
      transformIndexHtml: { order: 'pre', handler: (html: string) => html.replace('/src/main.tsx', '/src/native-pos/main.tsx') },
      generateBundle() { this.emitFile({type:'asset', fileName:'native-pos-build.json', source:JSON.stringify({product, environment:'uat', origin, version:`0.1.0-uat.${revision}`, versionCode:10000 + revision, autoLogin:false, offlinePayments:false})}); },
    }],
    resolve: { alias: [
      { find: '@/stores/auth.store', replacement: path.resolve(__dirname, 'src/native-pos/session.ts') },
      { find: './RetailRoutes', replacement: path.resolve(__dirname, `src/native-pos/${product === 'retail' ? 'Retail' : 'Restaurant'}Routes.tsx`) },
      { find: '@', replacement: path.resolve(__dirname, 'src') },
    ] },
    build: { outDir: `dist-native-${product}`, sourcemap: false },
    server: { host: '127.0.0.1', port: 3021, strictPort: true },
  };
});
