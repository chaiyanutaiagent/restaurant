import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { test } from 'node:test';

const source = readFileSync(new URL('../src/lib/deviceWorkspace.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { supportsDeviceType, counterSalesTarget } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);

test('Retail only offers Counter with matching database; restaurant keeps all device types', () => {
  const retail = { business_type: 'retail_pos', target_database: 'retail_pos' };
  const restaurant = { business_type: 'restaurant', target_database: 'restaurant' };
  assert.equal(supportsDeviceType(retail, 'counter'), true);
  for (const type of ['kitchen', 'pickup']) assert.equal(supportsDeviceType(retail, type), false);
  for (const type of ['counter', 'kitchen', 'pickup']) assert.equal(supportsDeviceType(restaurant, type), true);
  assert.equal(supportsDeviceType({ ...retail, target_database: 'restaurant' }, 'counter'), false);
  assert.equal(supportsDeviceType({ business_type: null, target_database: null }, 'counter'), false);
});

test('Counter uses the sales route and permission of its server context', () => {
  assert.deepEqual(counterSalesTarget({ business_type: 'retail_pos', target_database: 'retail_pos' }), { path: '/retail/pos', permission: 'pos.sale.create' });
  assert.deepEqual(counterSalesTarget({ business_type: 'restaurant', target_database: 'restaurant' }), { path: '/counter/orders', permission: 'fb.order.create' });
  assert.equal(counterSalesTarget({ business_type: 'retail_pos', target_database: 'restaurant' }), null);
});
