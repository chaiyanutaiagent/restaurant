// Overlay only this release onto the preserved, currently deployed UAT source.
import fs from 'node:fs';
import path from 'node:path';
const target = 'tmp/three-app-pairing-20261025/web';
if (!fs.existsSync(path.join(target, 'frontend/package.json'))) {
  throw new Error('Missing preserved UAT baseline. This historical overlay is not a clean-checkout production release builder.');
}
const files = [
  'frontend/src/components/pos/RetailWorkspaceNav.tsx',
  'frontend/src/components/pos/RetailWorkspaceHub.tsx',
  'frontend/src/pages/pos/POSPage.tsx',
  'frontend/src/lib/printerQueue.ts',
  'frontend/src/lib/saveCsv.ts',
  'frontend/tests/save-csv.test.mjs',
  'frontend/native-pos-android/NativeDocumentPrinter.java',
  'frontend/android-retail/app/src/main/AndroidManifest.xml',
  'frontend/src/lib/takeawayPrinter.ts',
  'frontend/native-pos-android/TakeawayPrinterPlugin.java',
  'frontend/native-pos-android/BluetoothPrintDeadline.java',
  'frontend/native-pos-android-tests/BluetoothPrintDeadlineTest.java',
  'frontend/tests/printer-queue.test.mjs',
  'frontend/src/pages/products/RetailProductIntakePage.tsx',
  'frontend/src/components/products/RetailProductOptions.tsx',
  'frontend/src/components/products/RetailUnitCreateDialog.tsx',
  'frontend/e2e/retail-intake.spec.ts',
  'frontend/src/pages/stock/RetailTransfersPage.tsx',
  'frontend/src/pages/reports/RetailSkuReportPage.tsx',
  'frontend/src/native-pos/RetailRoutes.tsx',
  'frontend/src/native-pos/main.tsx',
  'frontend/src/native-pos/Device.tsx',
  'frontend/src/index.css',
  'frontend/src/lib/pairingAppDownloads.ts',
  'frontend/e2e/native-pos.spec.ts',
  'frontend/e2e/retail-workspace.spec.ts',
  'frontend/native-pos-android/uat.gradle',
  'frontend/vite.native-pos.config.ts',
  'scripts/build-native-pos.mjs',
];
for (const file of files) {
  const dest = path.join(target,file);
  fs.mkdirSync(path.dirname(dest),{recursive:true});
  fs.copyFileSync(file,dest);
}
// App.tsx alone overlaps unfinished LINE OA. Exclude its imports/routes.
const app = fs.readFileSync('frontend/src/App.tsx','utf8').split('\n')
  .filter(line => !/LineOa(Page|LinkPage)/.test(line)).join('\n');
fs.writeFileSync(path.join(target,'frontend/src/App.tsx'),app);
console.log('Staged scoped Retail UI and UAT.14 metadata; LINE OA excluded.');
