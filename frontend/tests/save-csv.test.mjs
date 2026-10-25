import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';

async function nativeSaver(saveCsv) {
  const source=fs.readFileSync(new URL('../src/lib/saveCsv.ts',import.meta.url),'utf8')
    .replace(/import .* from '@capacitor\/core';/, 'const { Capacitor, registerPlugin } = globalThis.__csvTest;');
  globalThis.__csvTest={Capacitor:{isNativePlatform:()=>true},registerPlugin:()=>({shareCsv:saveCsv})};
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText;
  const module=await import('data:text/javascript;base64,'+Buffer.from(code+`\n// ${Math.random()}`).toString('base64'));
  delete globalThis.__csvTest;
  return module.saveCsv;
}

test('Android shares UTF-8 BOM and content, without browser download',async()=>{
  let received;
  const save=await nativeSaver(async(options)=>{received=options;return {opened:true};});
  assert.equal(await save('retail-sku.csv','"สินค้า","ราคา"\r\n"เสื้อ",25'),'share-opened');
  assert.deepEqual(received,{filename:'retail-sku.csv',content:'\uFEFF"สินค้า","ราคา"\r\n"เสื้อ",25'});
});
test('An unopened share menu is not reported as success',async()=>{
  const save=await nativeSaver(async()=>({opened:false}));
  await assert.rejects(()=>save('retail.csv','data'),/Unable to open/);
});
test('Native failure propagates without silent browser fallback or retry',async()=>{
  let calls=0;
  const save=await nativeSaver(async()=>{calls++;throw new Error('Disk full');});
  await assert.rejects(()=>save('retail.csv','data'),/Disk full/);
  assert.equal(calls,1);
});
