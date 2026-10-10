import { test, expect, type Page } from "@playwright/test";

export async function captureThermalPrint(page: Page): Promise<void> {
  await page.addInitScript(() => {
    (window as any).__thermalPrints = [];
    const append = Node.prototype.appendChild;
    Node.prototype.appendChild = function<T extends Node>(node: T): T {
      const result = append.call(this, node) as T;
      if (node instanceof HTMLIFrameElement) {
        const bind = () => {
          if (!node.contentWindow) return;
          node.contentWindow.print = () => {
            const doc = node.contentDocument!, win = node.contentWindow!;
            const root = doc.querySelector<HTMLElement>(".takeaway-thermal-sheet")!;
            const rect = root.getBoundingClientRect();
            (window as any).__thermalPrints.push({
              text: root.textContent, bodyText: doc.body.textContent,
              height: rect.height, width: rect.width, scrollWidth: root.scrollWidth,
              paddingBottom: parseFloat(win.getComputedStyle(root).paddingBottom),
              visibility: win.getComputedStyle(root).visibility,
              pageStyle: doc.querySelector('[data-takeaway-slip-page]')?.textContent,
              imagesReady: Array.from(root.querySelectorAll('img')).every(i => i.complete && i.naturalWidth > 0),
            });
          };
        };
        bind(); node.addEventListener("load", bind);
      }
      return result;
    };
  });
}

for (const kind of ["customer", "merchant", "wap-customer", "wap-kitchen"]) {
  for (const long of [false, true]) {
    test(`thermal ${kind} ${long ? "long wrapped" : "short"} browser slip fits footer and feed`, async ({ page }) => {
      await captureThermalPrint(page);
      await page.goto(`/e2e/thermal-print-fixture.html?kind=${kind}${long ? "&long=1" : ""}`);
      await page.getByRole("button", { name: "Print fixture" }).click();
      await expect.poll(() => page.evaluate(() => (window as any).__thermalPrints.length)).toBe(1);
      const result = await page.evaluate(() => (window as any).__thermalPrints[0]);
      const mm = 96 / 25.4;
      const height = Number(result.pageStyle.match(/80mm\s+([\d.]+)mm/)[1]);
      expect(result.width / mm).toBeCloseTo(64, 1);
      expect(result.scrollWidth).toBeLessThanOrEqual(Math.ceil(result.width));
      expect(result.paddingBottom / mm).toBeCloseTo(15, 1);
      expect(height).toBeGreaterThan(result.height / mm);
      expect(result.visibility).toBe("visible");
      expect(result.imagesReady).toBe(true);
      expect(result.bodyText).not.toContain("DO NOT PRINT PAGE UI");
      expect(result.text).toContain(kind === "wap-kitchen" ? "ทำสินค้าแล้วส่งกลับเคาน์เตอร์" : kind === "wap-customer" ? "นำสลิปนี้ไปรับสินค้าที่เคาน์เตอร์" : "นำเลขคิวไปรับสินค้าที่เคาน์เตอร์");
      if (long) expect(height).toBeGreaterThan(300);
    });
  }
}

test("thermal ESC/POS short and long raster preserve footer whitespace and a single feed/cut", async ({ page }) => {
  for (const long of [false, true]) {
    await page.goto(`/e2e/thermal-print-fixture.html${long ? '?long=1' : ''}`);
    await expect.poll(() => page.evaluate(() => typeof (window as any).buildRaster)).toBe("function");
    for (const copy of ["customer", "merchant", "kitchen", "wap-customer"]) {
      const result = await page.evaluate(copy => (window as any).buildRaster(copy), copy);
      expect(result.widthBytes).toBe(72); // 576-dot, 80mm ESC/POS head
      expect(result.size).toBe(10 + result.widthBytes * result.height + 7);
      expect(result.blankRows).toBeGreaterThanOrEqual(72);
      expect(result.suffix).toEqual([27, 100, 4, 29, 86, 65, 16]);
      expect(result.footerText.join(' ')).toContain(copy === "kitchen" ? "ทำสินค้าแล้วส่งกลับเคาน์เตอร์" : copy === "wap-customer" ? "นำสลิปนี้ไปรับสินค้าที่เคาน์เตอร์" : "นำเลขคิวไปรับสินค้าที่เคาน์เตอร์");
      if (long) expect(result.height / 8).toBeGreaterThan(300);
    }
  }
});

for (const historyFailure of [false, true]) {
test(`thermal Takeaway reprint confirms history once, cancel records nothing, QR isolated (history failure=${historyFailure})`, async ({ page }) => {
  const company = '11111111-1111-4111-8111-111111111111';
  const brand = '33333333-3333-4333-8333-333333333333';
  const branch = '22222222-2222-4222-8222-222222222222';
  const accessToken = `header.${Buffer.from(JSON.stringify({ permissions: ['*'], scope_types: ['branch'], brand_id: brand, branch_id: branch, business_type: 'takeaway', target_database: 'takeaway' })).toString('base64url')}.signature`;
  await page.addInitScript(({ company, brand, branch, accessToken }) => {
    Object.defineProperty(navigator, 'usb', { configurable: true, value: { getDevices: async () => [] } });
    localStorage.setItem('erp-auth', JSON.stringify({ version: 0, state: {
      accessToken, refreshToken: 'test', companyId: company, brandId: brand, branchId: branch,
      businessSlug: 'test', businessType: 'takeaway', targetDatabase: 'takeaway', scopeTypes: ['branch'], stationKey: null, permissions: ['*'],
      user: { id: '44444444-4444-4444-8444-444444444444', company_id: company, username: 'test', display_name: 'Tester', is_active: true, is_superuser: false },
    } }));
  }, { company, brand, branch, accessToken });
  await captureThermalPrint(page);
  const receipt = { id: 'receipt', order_id: 'existing-order', receipt_number: 'TR-EXISTING', issued_at: '2026-10-10T12:00:00Z', print_count: 0,
    payload: { order_number: 'TW-EXISTING', queue_number: 88, subtotal: '100', discount_amount: '0', tax_amount: '7', total_amount: '107', payment_method: 'cash', items: [{ sku: 'TEST', name: 'หมูย่าง', quantity: '1', line_total: '100' }] } };
  const mutations: string[] = [];
  const printKeys: string[] = [];
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url());
    if (route.request().method() !== 'GET') mutations.push(url.pathname);
    let data: unknown = [];
    if (url.pathname.endsWith('/takeaway/status')) data = { enabled: true, writes_enabled: true, company_id: company, brand_id: brand, branch_id: branch, fulfillment_mode: 'counter_combined' };
    else if (url.pathname.endsWith('/takeaway/shifts')) data = [{ id: 'shift', status: 'open', round_no: 1 }];
    else if (url.pathname.endsWith('/takeaway/orders')) data = url.searchParams.has('fulfillment_status') ? [] : [{ id: 'existing-order', status: 'paid', fulfillment_status: 'picked_up', queue_number: 88, total_amount: '107' }];
    else if (url.pathname.endsWith('/receipt')) data = receipt;
    else if (url.pathname.endsWith('/receipt/prints')) {
      printKeys.push(route.request().postDataJSON().idempotency_key);
      if (historyFailure) {
        await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Simulated history failure' }) });
        return;
      }
      data = { ...receipt, print_count: printKeys.length };
    } else if (url.pathname.endsWith('/ordering-links')) data = { token: 'TEST-ONLY-QR', expires_at: '2026-10-11T00:00:00Z' };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ data, meta: {}, error: null }) });
  });
  await page.goto('/takeaway/store/orders');
  await page.getByRole('button', { name: /คิว 88/ }).click();
  await expect(page.getByRole('button', { name: 'ไม่ได้พิมพ์', exact: true })).toBeVisible();
  expect(printKeys).toHaveLength(0);
  // Another print while confirmation is pending must not produce a second job.
  await page.getByRole('button', { name: 'ใบลูกค้า', exact: true }).click();
  expect(await page.evaluate(() => (window as any).__thermalPrints.length)).toBe(1);
  await page.getByRole('button', { name: 'ไม่ได้พิมพ์', exact: true }).click();
  for (const [copy, label] of [['ใบลูกค้า', 'ใบเสร็จลูกค้า'], ['สำเนาร้าน', 'สำเนาร้าน']]) {
    await page.getByRole('button', { name: copy, exact: true }).click();
    await expect(page.getByRole('button', { name: 'ยืนยันพิมพ์แล้ว', exact: true })).toBeVisible();
    const printed = await page.evaluate(() => (window as any).__thermalPrints.at(-1));
    expect(printed.text).toContain(label);
    await page.getByRole('button', { name: 'ยืนยันพิมพ์แล้ว', exact: true }).click();
    await expect(page.getByRole('button', { name: 'ยืนยันพิมพ์แล้ว', exact: true })).toHaveCount(0);
    await expect.poll(() => printKeys.length).toBe(copy === 'ใบลูกค้า' ? 1 : 2);
    if (historyFailure) await expect(page.getByText('พิมพ์แล้ว แต่บันทึกประวัติไม่สำเร็จ').first()).toBeVisible();
  }
  await page.getByRole('button', { name: 'QR ลูกค้าสั่งเอง', exact: true }).click();
  await page.getByRole('button', { name: 'พิมพ์ QR', exact: true }).click();
  await expect.poll(() => page.evaluate(() => (window as any).__thermalPrints.length)).toBe(4);
  const qr = await page.evaluate(() => (window as any).__thermalPrints.at(-1));
  expect(qr.imagesReady).toBe(true);
  expect(qr.text).toContain('สแกนเลือกสินค้า');
  expect(qr.bodyText).not.toContain('ตะกร้า');
  expect(qr.bodyText).not.toContain('TR-EXISTING');
  expect(Number(qr.pageStyle.match(/80mm\s+([\d.]+)mm/)[1])).toBeGreaterThan(qr.height * 25.4 / 96);
  expect(new Set(printKeys).size).toBe(2);
  expect(mutations.filter(path => !path.endsWith('/receipt/prints') && !path.endsWith('/ordering-links'))).toEqual([]);
});
}

test('thermal failed QR image prevents printing instead of producing a blank QR', async ({ page }) => {
  await page.goto('/e2e/thermal-print-fixture.html');
  const message = await page.evaluate(async () => {
    const { waitForSlipImages } = await import('/src/lib/takeawaySlipPrint.ts');
    const root = document.createElement('div');
    root.innerHTML = '<img src="data:image/png;base64,broken" />';
    try { await waitForSlipImages(root); return 'unexpected success'; }
    catch { return 'blocked'; }
  });
  expect(message).toBe('blocked');
});
