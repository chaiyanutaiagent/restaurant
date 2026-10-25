import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
import {test} from 'node:test';
const js=ts.transpileModule(readFileSync(new URL('../src/lib/printerQueue.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
const {createPrinterQueue}=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
test('drawer completes before receipt; a failed job is not retried and queue recovers',async()=>{
  const enqueue=createPrinterQueue(),events=[];
  let release;
  const gate=new Promise(resolve=>{release=resolve;});
  const drawer=enqueue(async()=>{events.push('drawer:start');await gate;events.push('drawer:done');});
  const receipt=enqueue(async()=>{events.push('receipt');});
  await Promise.resolve();assert.deepEqual(events,['drawer:start']);
  release();await Promise.all([drawer,receipt]);
  assert.deepEqual(events,['drawer:start','drawer:done','receipt']);
  await assert.rejects(enqueue(async()=>{events.push('failed');throw Error('timeout');}));
  await enqueue(async()=>{events.push('next');});
  assert.deepEqual(events,['drawer:start','drawer:done','receipt','failed','next']);
});
