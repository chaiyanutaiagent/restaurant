import { test, expect, type Page } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const branchId = "22222222-2222-4222-8222-222222222222";
async function setup(page: Page, readonly = false): Promise<{ writes: string[] }> {
  const writes: string[] = [];
  await page.addInitScript(({ companyId, branchId, readonly }) => {
    localStorage.setItem("erp-auth", JSON.stringify({ state: {
      accessToken: "local-credit-test", refreshToken: "local-refresh",
      user: { id: "tester", company_id: companyId, username: "tester", display_name: "Credit tester", is_active: true },
      companyId, branchId, permissions: readonly ? ["accounting.invoice.view"] : ["*"],
      scopeTypes: ["company", "branch"], businessType: "restaurant", targetDatabase: "restaurant", stationKey: null,
    }, version: 0 }));
  }, { companyId, branchId, readonly });
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (request.method() !== "GET") writes.push(request.postData() ?? "");
    let data: unknown = [];
    if (path.endsWith("/company/context")) data = { contract_version: "2026-09-19.1", environment: "uat",
      company: { id: companyId, name: "บริษัททดสอบขายเชื่อ" }, branch: { id: branchId, code: "BKK-01", name: "สาขาทดสอบ" }, brand: null,
      business_type: "restaurant", target_database: "restaurant", currency: "THB", timezone: "Asia/Bangkok", tax: {},
      all_scope_allowed: { brand: true, branch: true, station: false }, updated_at: new Date().toISOString() };
    else if (path.endsWith("/company/action-center")) data = { items: [], total: 0, unread: 0 };
    else if (path.endsWith("/credit-sales/options")) data = {
      customers: [{ id: "customer-1", code: "C1", name: "ลูกค้าทดสอบ" }], products: [{ id: "product-1", name: "ชุดอาหารจัดเลี้ยง", price: "107", vat_type: "included" }], locations: [], notice: "ชุดข้อมูลจำลอง" };
    else if (path.endsWith("/credit-sales")) {
      if (request.method() === "POST") return route.fulfill({ status: 409, json: { detail: "ยังไม่บันทึก ทดลองกดซ้ำด้วยคำขอเดิม" } });
      data = { items: [], has_more: false };
    }
    return route.fulfill({ json: { data, error: null } });
  });
  return { writes };
}

test("tablet credit sales form, error retry idempotency and offline safety", async ({ page, context }, testInfo) => {
  const { writes } = await setup(page);
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/company/credit-sales");
  await expect(page.getByRole("heading", { name: "ขายเชื่อและลูกหนี้", exact: true })).toBeVisible();
  await page.getByLabel("ลูกค้า", { exact: true }).selectOption("customer-1");
  await page.getByLabel("ชื่องาน", { exact: true }).fill("จัดเลี้ยงทดสอบ");
  await page.getByLabel("กำหนดชำระ", { exact: true }).fill("2026-12-31");
  await page.getByLabel("สินค้า 1", { exact: true }).selectOption("product-1");
  await page.getByRole("button", { name: "สร้างร่าง", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("ยังไม่บันทึก");
  await page.getByRole("button", { name: "สร้างร่าง", exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(JSON.parse(writes[0]).request_key).toBe(JSON.parse(writes[1]).request_key);
  expect(writes[0]).not.toContain("unit_price");
  expect(await page.getByTestId("credit-sales").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("credit-sales-tablet.png"), animations: "disabled" });
  await context.setOffline(true);
  await expect(page.getByTestId("credit-sales")).toContainText("ออฟไลน์");
  await expect(page.getByRole("button", { name: "สร้างร่าง", exact: true })).toHaveCount(0);
});

test("viewer has no creation controls and opening makes no writes", async ({ page }) => {
  const { writes } = await setup(page, true);
  await page.goto("/company/credit-sales");
  await expect(page.getByText("ยังไม่มีรายการขายเชื่อ")).toBeVisible();
  await expect(page.getByRole("button", { name: "สร้างร่าง", exact: true })).toHaveCount(0);
  expect(writes).toEqual([]);
});
