/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_COMPANY_ID?: string;
  readonly VITE_BUSINESS_SLUG?: string;
  readonly VITE_PUBLIC_APP_ORIGIN?: string;
  readonly VITE_UAT_AUTO_LOGIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
