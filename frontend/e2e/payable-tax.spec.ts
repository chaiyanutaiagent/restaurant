import { expect, test, type Page } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const branchId = "22222222-2222-4222-8222-222222222222";
const supplierId = "33333333-3333-4333-8333-333333333333";
const invoiceId = "44444444-4444-4444-8444-444444444444";

async function setup(page: Page, mode = "normal") {
  const writes: Record<string, any>[] = [];
  await page.addInitScript(({ companyId, branchId }) => {
    localStorage.setItem("erp-auth", JSON.stringify({ state: {
      accessToken: "local-tax-test", refreshToken: "local-refresh",
      user: { id: "55555555-5555-4555-8555-555555555555", company_id: companyId, username: "tax.test", is_active: true },
      companyId, branchId, permissions: ["*"], scopeTypes: ["company", "branch"],
      brandId: null, stationKey: null, businessType: "restaurant", targetDatabase: "restaurant"
    }, version: 0 }));
  }, { companyId, branchId });
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    let data: unknown = [];
    if (path.endsWith("/payable/invoices")) {
      data = [{ id: invoiceId, supplier_id: supplierId, supplier_name: "ผู้จำหน่ายทดสอบ", invoice_number: "SINV-TEST",
        status: "unpaid", subtotal: 1000, vat_amount: 70, wht_amount: mode === "legacy" ? 30 : 0,
        total_amount: 1070, paid_amount: 0, remaining_amount: 1070, invoice_date: "2026-10-01", due_date: "2026-10-31", input_vat_claimable: true }];
    } else if (path.endsWith("/purchase/suppliers")) {
      data = [{ id: supplierId, name: "ผู้จำหน่ายทดสอบ", wht_rate: 3, wht_type: "บริการ", payment_term_days: 30 }];
    } else if (path.endsWith("/payable/payments/preview")) {
      if (mode === "legacy") return route.fulfill({ status: 409, json: { detail: "ใบแจ้งหนี้เดิมหัก WHT ตอนตั้งหนี้แล้ว กรุณาให้บัญชีตรวจทาน" } });
      const rows = req.postDataJSON().allocations.map((row: any) => {
        const base = row.wht_rate === 0 ? 0 : row.wht_base_amount ?? Math.round(row.allocated_amount / 1.07 * 100) / 100;
        const wht = Math.round(base * row.wht_rate) / 100;
        return { ...row, wht_base_amount: base, wht_amount: wht, net_amount: row.allocated_amount - wht };
      });
      data = { allocations: rows, total_allocated: rows.reduce((sum: number, row: any) => sum + row.allocated_amount, 0),
        total_wht: rows.reduce((sum: number, row: any) => sum + row.wht_amount, 0), net_amount: rows.reduce((sum: number, row: any) => sum + row.net_amount, 0) };
    } else if (path.endsWith("/payable/payments") && req.method() === "POST") {
      writes.push(req.postDataJSON());
      if (mode === "retry" && writes.length === 1) return route.abort("failed");
      data = { payment_number: "PAY-TEST" };
    } else if (path.endsWith("/company/context")) {
      data = { company: { id: companyId, name: "บริษัททดสอบ" }, branch: { id: branchId, name: "ทดสอบ" },
        brand: null, business_type: "restaurant", target_database: "restaurant", all_scope_allowed: {}, tax: {} };
    } else if (path.endsWith("/company/action-center")) {
      data = { items: [], total: 0, unread: 0 };
    }
    return route.fulfill({ json: { data, meta: { total: 1 }, error: null } });
  });
  await page.goto("/payable");
  await page.getByRole("button", { name: "จ่าย", exact: true }).click();
  return writes;
}

test("partial WHT server preview and explicit confirmation on desktop/tablet", async ({ page }) => {
  const writes = await setup(page);
  const dialog = page.getByRole("dialog");
  const save = dialog.getByRole("button", { name: "บันทึกการจ่าย", exact: true });
  await expect(save).toBeDisabled();
  await expect(page.getByLabel("อัตรา WHT 1", { exact: true })).toHaveValue("0.00");
  await page.getByLabel("ยอดตัดหนี้ 1", { exact: true }).fill("535");
  await page.getByLabel("อัตรา WHT 1", { exact: true }).fill("3");
  await page.getByLabel("ประเภทเงินได้ 1", { exact: true }).fill("ค่าบริการ");
  await expect(dialog.getByText("520.00", { exact: true }).first()).toBeVisible();
  for (const width of [1440, 820, 1024]) {
    await page.setViewportSize({ width, height: 1180 });
    await expect(save).toBeVisible();
    expect(await dialog.evaluate((node) => node.scrollWidth <= node.clientWidth + 1)).toBe(true);
  }
  await dialog.getByRole("checkbox").check();
  await save.click();
  await expect(dialog).toHaveCount(0);
  expect(writes).toHaveLength(1);
  expect(writes[0].allocations[0]).toMatchObject({ allocated_amount: 535, wht_base_amount: 500, wht_amount: 15 });
  expect(writes[0].wht_reviewed).toBe(true);
});

test("legacy pre-withheld invoices stay blocked", async ({ page }) => {
  const writes = await setup(page, "legacy");
  await page.getByLabel("ประเภทเงินได้ 1", { exact: true }).fill("ค่าบริการ");
  await expect(page.getByRole("dialog").getByText(/ต้องให้บัญชีตรวจทาน/)).toBeVisible();
  await expect(page.getByRole("button", { name: "บันทึกการจ่าย", exact: true })).toBeDisabled();
  expect(writes).toHaveLength(0);
});

test("uncertain network result replays same key and frozen payload", async ({ page }) => {
  const writes = await setup(page, "retry");
  await page.getByLabel("ประเภทเงินได้ 1", { exact: true }).fill("ซื้อสินค้า ไม่หัก");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("checkbox")).toBeEnabled();
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "บันทึกการจ่าย", exact: true }).click();
  await expect(page.getByLabel("ยอดตัดหนี้ 1", { exact: true })).toBeDisabled();
  await dialog.getByRole("button", { name: "ตรวจผลคำขอเดิม (ไม่จ่ายซ้ำ)", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(writes).toHaveLength(2);
  expect(writes[1]).toEqual(writes[0]);
});
