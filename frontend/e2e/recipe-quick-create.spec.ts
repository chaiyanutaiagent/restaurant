import { test, expect, type Page } from '@playwright/test';
const company = '11111111-1111-4111-8111-111111111111';
const brand = '22222222-2222-4222-8222-222222222222';
const product = { id: 'menu', name: 'ข้าวหมูย่าง', selling_price: 100, is_active: true, product_type: 'manufactured', unit: { code: 'PCS' } };
const pork = { id: 'pork', name: 'หมูสด', sku: 'PORK', cost_price: 165, inventory_role: 'central_raw', unit: { code: 'KG' } };
const recipe = { id: 'recipe', product_id: 'menu', product_name: product.name, name: 'สูตรเดิม', recipe_type: 'menu_recipe',
  version_no: 1, is_active: true, yield_qty: 1, yield_unit: 'จาน', loss_percent: 0, total_cost: 16.5, cost_per_yield: 16.5,
  selling_price: 100, gross_margin_pct: 83.5, effective_yield_qty: 1,
  ingredients: [{ id: 'line', ingredient_id: pork.id, ingredient_name: pork.name, ingredient_sku: pork.sku, quantity: 100, unit: 'g', cost_unit: 'KG', latest_unit_cost: 165, normalized_quantity: 0.1, cost_per_recipe: 16.5 }] };

async function setup(page: Page, { failQuick = false, failSave = false, existing = false, permissions = ['*'] } = {}) {
  const token = `h.${Buffer.from(JSON.stringify({ permissions, business_type: 'restaurant', target_database: 'restaurant', brand_id: brand, branch_id: '33333333-3333-4333-8333-333333333333' })).toString('base64url')}.s`;
  await page.addInitScript(({ token, company, brand, permissions }) => localStorage.setItem('erp-auth', JSON.stringify({ version: 0, state: {
    accessToken: token, refreshToken: 'test', companyId: company, brandId: brand, branchId: '33333333-3333-4333-8333-333333333333', targetDatabase: 'restaurant',
    businessSlug: 'test', businessType: 'restaurant', scopeTypes: ['company'], permissions,
    user: { id: 'user', company_id: company, username: 'owner', display_name: 'Owner', is_active: true },
  } })), { token, company, brand, permissions });
  const creates: any[] = [], saves: any[] = [], unexpected: string[] = [];
  let quickAttempts = 0, saveAttempts = 0;
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url());
    let data: unknown = [], status = 200;
    if (url.pathname.endsWith('/recipe-products')) data = url.searchParams.has('product_type') ? [pork] : [product];
    else if (url.pathname.endsWith('/raw-materials/quick-create')) {
      const body = request.postDataJSON(); creates.push(body); quickAttempts++;
      if (failQuick && quickAttempts === 1) { await route.fulfill({ status: 503, json: { detail: 'ลองใหม่ ข้อมูลยังอยู่' } }); return; }
      data = { id: 'new-raw', ...body, unit: { code: body.unit.toUpperCase() }, inventory_setup: { zero_balances_created: 1, mapping_created: body.use_company_kitchen } };
    } else if (url.pathname.endsWith('/recipes') && request.method() === 'POST' || url.pathname.endsWith('/recipes/recipe') && request.method() === 'PATCH') {
      saves.push(request.postDataJSON()); saveAttempts++;
      if (failSave && saveAttempts === 1) { await route.fulfill({ status: 503, json: { detail: 'ระบบไม่พร้อมชั่วคราว' } }); return; }
      data = recipe;
    } else if (url.pathname.endsWith('/recipes')) data = existing ? [recipe] : [];
    else if (url.pathname.endsWith('/recipes/recipe')) data = recipe;
    else if (request.method() !== 'GET') unexpected.push(url.pathname);
    if (url.pathname.endsWith('/company-kitchen/dashboard')) data = {
      kitchen: { name: 'ครัวกลาง', branch_id: 'central', raw_location_id: 'raw', timezone: 'Asia/Bangkok' }, write_enabled: true,
      release: { writes_enabled: true, release_stage: 'uat', generated_at: new Date().toISOString(), stale_after_seconds: 300, checks: [], hard_holds: [] },
      ingredients: [], aliases: [], demands: [], orders: [], setup_options: { branches: [], locations: [], products: [], brand_branches: [], brands: [{ id: brand, slug: 'test', name: 'แบรนด์ทดสอบ', business_type: 'restaurant' }] },
    };
    if (url.pathname.includes('/company-kitchen/report')) data = { production_by_brand: [], ingredient_usage: [] };
    await route.fulfill({ status, json: { data, meta: {}, error: null } });
  });
  return { creates, saves, unexpected };
}
async function start(page: Page) {
  await page.goto('/restaurant/recipes');
  await page.getByRole('button', { name: 'สร้างสูตรใหม่', exact: true }).click();
  await page.getByRole('combobox', { name: 'เมนูหน้าร้าน', exact: true }).selectOption('menu');
  await page.getByRole('button', { name: 'เพิ่มวัตถุดิบ', exact: true }).click();
}

test('recipe existing ingredient kg/g, yield and loss; save does not update master costs', async ({ page }) => {
  const calls = await setup(page); await start(page);
  await page.getByRole('combobox', { name: 'ค้นหาวัตถุดิบ' }).fill('หมู');
  await page.getByRole('option', { name: 'หมูสด · KG' }).click();
  await page.getByLabel('ปริมาณ', { exact: true }).fill('100');
  await page.getByLabel('หน่วย', { exact: true }).fill('g');
  await expect(page.getByTestId('recipe-total-cost')).toHaveText('฿16.50');
  await page.getByLabel('สูญเสีย (%)').fill('10');
  await expect(page.getByTestId('recipe-unit-cost')).toHaveText('฿18.33');
  await page.getByRole('button', { name: 'บันทึกสูตร', exact: true }).click();
  await expect.poll(() => calls.saves.length).toBe(1);
  expect(calls.saves[0].ingredients[0]).toMatchObject({ ingredient_id: 'pork', quantity: 100, unit: 'g' });
  expect(calls.unexpected).toEqual([]);
});

for (const viewport of [{ width: 1024, height: 768 }, { width: 390, height: 844 }]) {
  test(`recipe quick-create and save retry retain draft and focus at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const calls = await setup(page, { failQuick: true, failSave: true }); await start(page);
    await page.getByRole('combobox', { name: 'ค้นหาวัตถุดิบ' }).fill('กะทิใหม่');
    await page.getByRole('button', { name: 'สร้างวัตถุดิบใหม่', exact: true }).click();
    const modal = page.getByRole('dialog');
    await modal.getByRole('combobox', { name: 'หน่วยสต็อก', exact: true }).selectOption('l');
    await modal.getByLabel('ต้นทุนต่อ l').fill('80');
    await modal.getByRole('button', { name: 'สร้างและเลือกใช้' }).click();
    await expect(modal.getByRole('alert')).toContainText('ข้อมูลที่กรอกยังอยู่');
    await expect(modal.getByLabel('ชื่อวัตถุดิบ', { exact: true })).toHaveValue('กะทิใหม่');
    await modal.getByRole('button', { name: 'สร้างและเลือกใช้' }).click();
    await expect(modal).toHaveCount(0);
    await expect(page.getByLabel('ปริมาณ', { exact: true })).toBeFocused();
    expect(calls.creates[0].idempotency_key).toBe(calls.creates[1].idempotency_key);
    await page.getByLabel('ปริมาณ', { exact: true }).fill('500');
    await page.getByLabel('หน่วย', { exact: true }).fill('ml');
    await expect(page.getByTestId('recipe-total-cost')).toHaveText('฿40.00');
    await page.getByRole('button', { name: 'บันทึกสูตร', exact: true }).click();
    await expect(page.getByText('ระบบไม่พร้อมชั่วคราว').first()).toBeVisible();
    await expect(page.getByLabel('ปริมาณ', { exact: true })).toHaveValue('500');
    await page.getByRole('button', { name: 'บันทึกสูตร', exact: true }).click();
    await expect.poll(() => calls.saves.length).toBe(2);
    expect(calls.saves[1]).toEqual(calls.saves[0]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
  });
}

test('recipe duplicate suggestion selects existing; cross-dimension units block save', async ({ page }) => {
  const calls = await setup(page); await start(page);
  await page.getByRole('combobox', { name: 'ค้นหาวัตถุดิบ' }).fill('หมูสด');
  await page.getByRole('button', { name: 'สร้างวัตถุดิบใหม่', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('button', { name: 'สร้างและเลือกใช้' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'หมูสด', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByLabel('ปริมาณ', { exact: true })).toBeFocused();
  await page.getByLabel('หน่วย', { exact: true }).fill('ml');
  await expect(page.getByLabel('หน่วย', { exact: true })).toHaveValue('ml');
  await expect(page.getByTestId('recipe-ingredient-row').getByRole('alert')).toContainText('แปลงเป็น');
  await page.getByRole('button', { name: 'บันทึกสูตร', exact: true }).click();
  expect(calls.creates).toHaveLength(0); expect(calls.saves).toHaveLength(0);
});

test('recipe edit preserves ingredient costing unit and uses PATCH', async ({ page }) => {
  const calls = await setup(page, { existing: true });
  await page.goto('/restaurant/recipes');
  await page.getByRole('button').filter({ hasText: 'สูตรเดิม' }).click();
  await page.getByRole('button', { name: 'แก้ไขสูตร', exact: true }).click();
  await expect(page.getByTestId('recipe-total-cost')).toHaveText('฿16.50');
  await page.getByLabel('ปริมาณ', { exact: true }).fill('200');
  await page.getByRole('button', { name: 'อัปเดตสูตร', exact: true }).click();
  await expect.poll(() => calls.saves.length).toBe(1);
  expect(calls.saves[0].ingredients[0].quantity).toBe(200); expect(calls.unexpected).toEqual([]);
});

test('company kitchen embeds production recipe and quick-creates canonical material with mapping', async ({ page }) => {
  const calls = await setup(page); await page.goto('/company-kitchen');
  await page.getByRole('tab', { name: 'สูตรผลิตครัวกลาง', exact: true }).click();
  await page.getByRole('combobox', { name: 'สูตรของแบรนด์', exact: true }).selectOption('test');
  await page.getByRole('button', { name: 'สร้างสูตรใหม่', exact: true }).click();
  await expect(page.getByRole('combobox', { name: 'ประเภทสูตร', exact: true })).toHaveValue('production_recipe');
  await page.getByRole('combobox', { name: 'สินค้าที่ผลิต', exact: true }).selectOption('menu');
  await page.getByRole('button', { name: 'เพิ่มวัตถุดิบ', exact: true }).click();
  await page.getByRole('combobox', { name: 'ค้นหาวัตถุดิบ' }).fill('น้ำตาลใหม่');
  await page.getByRole('button', { name: 'สร้างวัตถุดิบใหม่', exact: true }).click();
  await page.getByRole('button', { name: 'สร้างและเลือกใช้' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(calls.creates[0]).toMatchObject({ inventory_role: 'central_raw', use_company_kitchen: true, sku: '' });
  await page.getByRole('button', { name: 'บันทึกสูตร', exact: true }).click();
  await expect.poll(() => calls.saves.length).toBe(1);
  expect(calls.saves[0]).toMatchObject({ recipe_type: 'production_recipe', branch_id: null });
});

test('cashier cannot access recipe editor', async ({ page }) => {
  const calls = await setup(page, { permissions: ['pos.sale.create'] });
  await page.goto('/restaurant/recipes'); await expect(page).toHaveURL(/\/403$/);
  expect(calls.creates).toHaveLength(0); expect(calls.saves).toHaveLength(0);
});
