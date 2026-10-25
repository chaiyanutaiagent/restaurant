import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import path from 'node:path';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
const require=createRequire(path.resolve('frontend/package.json'));
const ts=require('typescript');
const compiled=ts.transpileModule(readFileSync('frontend/src/native-pos/updatePolicy.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText;
const {verifyPosRelease}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
for(const file of process.argv.slice(2)) {
  const m=JSON.parse(readFileSync(file,'utf8'));const product=m.package_id.split('.')[2];
  assert.deepEqual(await verifyPosRelease(m,product),m);
  for(const tampered of [{...m,version_code:m.version_code+1},{...m,apk_sha256:'0'.repeat(64)},{...m,channel:'production'},{...m,apk_url:m.apk_url.replace('.com/','.com.evil/')},{...m,signature:'AAAA'}])
    await assert.rejects(()=>verifyPosRelease(tampered,product));
  await assert.rejects(()=>verifyPosRelease(m,product==='retail'?'restaurant':'retail'));
  console.log(`${product}: signed release verified; six tamper/wrong-channel cases rejected`);
  if(process.env.FCS_VERIFY_PUBLIC==='true') {
    const download=url=>{
      const result=spawnSync('curl',['-4','-fSs','--retry','2','--connect-timeout','10',url],{maxBuffer:20*1024*1024});
      if(result.status!==0)throw Error('Public download failed: '+url);
      return result.stdout;
    };
    const host=product==='retail'?'uat-retail':'uat-pos';
    const published=JSON.parse(download(`https://${host}.foodchainservice.com/downloads/native-pos-updates/${product}.json`).toString());
    assert.deepEqual(await verifyPosRelease(published,product),m);
    assert.equal(createHash('sha256').update(download(published.apk_url)).digest('hex'),published.apk_sha256);
    console.log(`${product}: public update channel signature and APK SHA256 match`);
  }
}
