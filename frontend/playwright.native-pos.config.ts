import { defineConfig } from '@playwright/test';
const product=process.env.FCS_POS_PRODUCT;
if(!['retail','restaurant'].includes(product ?? ''))throw new Error('Select FCS_POS_PRODUCT');
export default defineConfig({
  testDir:'./e2e', testMatch:'native-pos.spec.ts', workers:1, retries:0, timeout:30000,
  reporter:[['line']], outputDir:`/private/tmp/fcs-native-${product}-tests`,
  use:{baseURL:'http://127.0.0.1:3021',channel:'chrome',viewport:{width:390,height:844}},
  webServer:{command:'npx vite --mode native-uat --config vite.native-pos.config.ts',url:'http://127.0.0.1:3021',reuseExistingServer:false},
});
