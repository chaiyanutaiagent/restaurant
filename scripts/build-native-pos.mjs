import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import {createHash} from 'node:crypto';

const product = process.argv[2];
if (!['retail','restaurant'].includes(product)) throw new Error('Usage: node scripts/build-native-pos.mjs retail|restaurant [--apk]');
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../frontend');
const env = {...process.env, FCS_POS_PRODUCT:product, CAPACITOR_UAT:'true'};
function run(command,args,cwd=frontend) {
  const result=spawnSync(command,args,{cwd,env,stdio:'inherit'});
  if(result.error)throw result.error;
  if(result.status!==0)process.exit(result.status ?? 1);
}
run('npx',['vite','build','--mode','native-uat','--config','vite.native-pos.config.ts']);
run('npx',['cap','sync','android']);
if(process.argv.includes('--apk')) {
  run('./gradlew',['assembleDebug','testDebugUnitTest','lintDebug'],path.join(frontend,`android-${product}`));
  const revision=product==='retail'?14:6;
  const version=`0.1.0-uat.${revision}`;
  const apk=path.join(frontend,`android-${product}/app/build/outputs/apk/debug/app-debug.apk`);
  const sdk=process.env.ANDROID_HOME || process.env.ANDROID_SDK_ROOT;
  if (!sdk) throw new Error('ANDROID_HOME is required for APK signature verification');
  run(path.join(sdk,'build-tools/35.0.0/apksigner'),['verify','--verbose',apk]);
  const directory=path.resolve(frontend,`../releases/uat/native-pos-${version}`);
  fs.mkdirSync(directory,{recursive:true});
  const filename=`foodchainservice-${product}-${version}.apk`;
  const bytes=fs.readFileSync(apk);
  fs.copyFileSync(apk,path.join(directory,filename));
  fs.writeFileSync(path.join(directory,`${product}-manifest.json`),JSON.stringify({
    product,version,versionCode:10000+revision,applicationId:`com.foodchainservice.${product}.uat`,filename,
    sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length,
    signing:'local-debug-UAT-only',production:false,physicalAcceptance:'pending',
    install:'Install over the previous UAT APK with the same signing certificate. Do not uninstall or clear storage with pending transactions.',
    rollback:'Stop transactions; reconcile pending outcomes. Rebuild last-known-good source with a higher versionCode and the same certificate. Do not downgrade/uninstall to force installation.'
  },null,2));
}
