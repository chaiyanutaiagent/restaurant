import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { test } from 'node:test';
const source = readFileSync(new URL('../src/lib/devicePairingLink.ts', import.meta.url), 'utf8');
const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { parseDevicePairingLink: parse, androidPairingIntent } = await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
const query = 'company_id=11111111-1111-4111-8111-111111111111&device_code=C-TEST123456&pin=123456&target_app=retail';
const url = `https://theloft.foodchainservice.com/device/pair?${query}`;
test('accept HTTPS QR and product-specific app link without trusting arbitrary origins', () => {
  assert.equal(parse(url, 'retail').pin, '123456');
  assert.equal(parse(`foodchainservice-retail-uat://pair?${query}`, 'retail').deviceCode, 'C-TEST123456');
  for (const invalid of [url.replace('https:', 'http:'), url.replace('theloft.foodchainservice.com', 'foodchainservice.com.evil.test'), url.replace('/device/pair', '/login'), url.replace('retail', 'restaurant'), url + '&pin=111111', url.replace('123456&target', '123&target'), url + '&expires_at=2020-01-01', url + '&branch_id=invalid', url.replace('https://', 'https://name:pass@')]) assert.throws(() => parse(invalid, 'retail'));
  assert.throws(() => parse(`foodchainservice-restaurant-uat://pair?${query}`, 'retail'));
});
test('Android intent locks package and encodes HTTPS fallback rather than accepting intent fragments', () => {
  const intent = androidPairingIntent(url, 'retail');
  assert.ok(intent.includes('scheme=foodchainservice-retail-uat;package=com.foodchainservice.retail.uat;'));
  assert.ok(intent.includes(`S.browser_fallback_url=${encodeURIComponent(url)};end`));
});
test('all three product-specific HTTPS App Links remain isolated and expire at the exact boundary', () => {
  const now = Date.now();
  for (const product of ['retail', 'restaurant', 'takeaway']) {
    const q = new URLSearchParams(query); q.set('target_app', product); q.set('expires_at', new Date(now + 86400000).toISOString());
    const link = `https://uat-app.foodchainservice.com/device/pair/${product}?${q}`;
    assert.equal(parse(link, product, now + 86399999).deviceCode, 'C-TEST123456');
    assert.throws(() => parse(link, product, now + 86400000));
    assert.ok(androidPairingIntent(link, product).includes(`package=com.foodchainservice.${product}.uat;`));
    for (const wrong of ['retail', 'restaurant', 'takeaway'].filter(p => p !== product)) assert.throws(() => parse(link, wrong, now));
  }
});
