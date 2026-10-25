import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./e2e', testMatch:['pairing-landing.spec.ts','retail-counter.spec.ts'], workers:1, retries:0,
  timeout:30000, reporter:[['line']], outputDir:'/private/tmp/fcs-pairing-landing',
  use:{baseURL:'http://127.0.0.1:3017',channel:'chrome'},
  webServer:{command:'npx vite --host 127.0.0.1 --port 3017 --strictPort',url:'http://127.0.0.1:3017',reuseExistingServer:false},
});
