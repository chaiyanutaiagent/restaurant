import {readFileSync,writeFileSync} from 'node:fs';
import {createHash,sign} from 'node:crypto';
const [buildManifest,apkPath,keyPath,outputPath]=process.argv.slice(2);
if(!outputPath)throw Error('Usage: create-native-pos-release build-manifest.json apk private-key-path output.json');
const build=JSON.parse(readFileSync(buildManifest,'utf8'));
if(!['retail','restaurant'].includes(build.product)||build.applicationId!==`com.foodchainservice.${build.product}.uat`
 || !Number.isSafeInteger(build.versionCode) || !/^\d+\.\d+\.\d+-uat\.\d+$/.test(build.version))throw Error('Invalid UAT build metadata');
const hash=createHash('sha256').update(readFileSync(apkPath)).digest('hex');
if(hash!==build.sha256)throw Error('APK differs from verified build');
const host=build.product==='retail'?'uat-retail':'uat-pos';
const payload={apk_sha256:hash,apk_url:`https://${host}.foodchainservice.com/downloads/native-pos-${build.version}/foodchainservice-${build.product}-${build.version}.apk`,channel:'uat',package_id:build.applicationId,published_at:new Date().toISOString(),version_code:build.versionCode,version_name:build.version};
const signature=sign('RSA-SHA256',Buffer.from(JSON.stringify(payload)),readFileSync(keyPath)).toString('base64');
writeFileSync(outputPath,JSON.stringify({...payload,signature},null,2)+'\n',{mode:0o644});
console.log(`Signed ${build.product} UAT ${build.version}; private key not included`);
