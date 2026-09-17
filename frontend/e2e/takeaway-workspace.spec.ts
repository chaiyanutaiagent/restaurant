import { expect, test, type Page, type Route } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const branchId = "22222222-2222-4222-8222-222222222222";

async function fulfill(route: Route, data: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ data, meta: { version: "test", target_database: "takeaway" }, error: null }),
  });
}

async function installSession(page: Page, permissions: string[], scopeTypes: string[]): Promise<void> {
  const payload = {
    permissions,
    scope_types: scopeTypes,
    branch_id: scopeTypes.includes("branch") || scopeTypes.includes("station") ? branchId : null,
    brand_id: "33333333-3333-4333-8333-333333333333",
    business_type: "takeaway",
    target_database: "takeaway",
  };
  const token = `header.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.signature`;
  await page.addInitScript(({ company, branch, sessionPermissions, sessionScopes, accessToken }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({
      state: {
        accessToken,
        refreshToken: "takeaway-refresh-token",
        user: {
          id: "44444444-4444-4444-8444-444444444444",
          company_id: company,
          username: "takeaway.user",
          email: null,
          phone: null,
          first_name: null,
          last_name: null,
          display_name: "Takeaway User",
          is_active: true,
          is_superuser: false,
          last_login_at: null,
        },
        companyId: company,
        businessSlug: "takeaway-test",
        brandId: "33333333-3333-4333-8333-333333333333",
        branchId: sessionScopes.includes("branch") || sessionScopes.includes("station") ? branch : null,
        businessType: "takeaway",
        targetDatabase: "takeaway",
        scopeTypes: sessionScopes,
        stationKey: sessionScopes.includes("station") ? "Kitchen" : null,
        permissions: sessionPermissions,
      },
      version: 0,
    }));
  }, { company: companyId, branch: branchId, sessionPermissions: permissions, sessionScopes: scopeTypes, accessToken: token });
}

async function mockTakeawayApi(page: Page): Promise<void> {
  await page.route("**/api/v1/**", (route) => fulfill(route, []));
  await page.route("**/api/v1/takeaway/status", (route) => fulfill(route, {
    enabled: true,
    company_id: companyId,
    brand_id: "33333333-3333-4333-8333-333333333333",
    branch_id: branchId,
  }));
}

test("branch cashier sees only the Store workspace and legacy counter redirects", async ({ page }) => {
  await installSession(page, [
    "takeaway.catalog.view",
    "takeaway.sale.create",
    "takeaway.shift.manage",
    "takeaway.pickup.manage",
  ], ["branch"]);
  await mockTakeawayApi(page);

  await page.goto("/takeaway");
  await expect(page.getByText("STORE", { exact: true })).toBeVisible();
  await expect(page.getByText("CENTRAL", { exact: true })).toHaveCount(0);
  await expect(page.getByText("ADMIN", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "ขายหน้าร้าน" })).toBeVisible();
  await expect(page.getByRole("link", { name: "กะขาย" })).toBeVisible();

  await page.goto("/takeaway/counter");
  await expect(page).toHaveURL(/\/takeaway\/store\/orders$/);
});

test("kitchen-only station lands on the first permitted Store page instead of 403", async ({ page }) => {
  await installSession(page, ["takeaway.kitchen.manage"], ["station"]);
  await mockTakeawayApi(page);

  await page.goto("/takeaway");
  await expect(page).toHaveURL(/\/takeaway\/store\/kitchen$/);
  await expect(page.getByRole("heading", { name: "คิวครัว" })).toBeVisible();
  await expect(page.getByText("CENTRAL", { exact: true })).toHaveCount(0);
});

test("brand manager gets Central and Admin routes but cannot enter Store scope", async ({ page }) => {
  await installSession(page, [
    "takeaway.catalog.view",
    "takeaway.central_order.manage",
    "takeaway.production.manage",
    "takeaway.stock.view",
    "takeaway.stock.manage",
    "takeaway.transfer.manage",
    "takeaway.credit.manage",
    "takeaway.report.view",
    "takeaway.import.dry_run",
    "takeaway.import.apply",
    "takeaway.erp.export",
    "takeaway.erp.acknowledge",
  ], ["brand"]);
  await mockTakeawayApi(page);

  await page.goto("/takeaway/central-orders");
  await expect(page).toHaveURL(/\/takeaway\/central\/orders$/);
  await expect(page.getByText("CENTRAL", { exact: true })).toBeVisible();
  await expect(page.getByText("ADMIN", { exact: true })).toBeVisible();
  await expect(page.getByText("STORE", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "ออเดอร์ถึงส่วนกลาง" })).toBeVisible();

  await page.goto("/takeaway/store/orders");
  await expect(page).toHaveURL(/\/403$/);
  await expect(page.getByRole("heading", { name: "ไม่มีสิทธิ์เข้าถึงหน้านี้" })).toBeVisible();
});

test("counter keeps a paid-first sale in the local outbox when network drops", async ({ page }) => {
  await installSession(page, [
    "takeaway.catalog.view",
    "takeaway.sale.create",
    "takeaway.sale.view",
    "takeaway.shift.manage",
  ], ["branch"]);
  await mockTakeawayApi(page);
  await page.route("**/api/v1/takeaway/catalog/categories**", (route) => fulfill(route, [
    { id: "55555555-5555-4555-8555-555555555555", name: "อาหาร", code: "food" },
  ]));
  await page.route("**/api/v1/takeaway/catalog/items**", (route) => fulfill(route, [
    {
      item: {
        id: "66666666-6666-4666-8666-666666666666",
        name: "หมูย่างทดสอบ",
        sku: "TEST-001",
        category_id: "55555555-5555-4555-8555-555555555555",
        price: "100.00",
        unit: "ชิ้น",
        tax_rate: "7.00",
      },
      effective_price: "100.00",
      is_available: true,
    },
  ]));
  await page.route("**/api/v1/takeaway/shifts", (route) => fulfill(route, [
    {
      id: "77777777-7777-4777-8777-777777777777",
      status: "open",
      round_no: 1,
      business_date: "2026-09-16",
      opening_cash: "500.00",
    },
  ]));
  await page.route("**/api/v1/takeaway/orders**", (route) => fulfill(route, []));

  await page.goto("/takeaway/store/orders");
  await expect(page.getByRole("button", { name: /หมูย่างทดสอบ/ })).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(window.navigator, "onLine", { configurable: true, get: () => false });
    window.dispatchEvent(new Event("offline"));
  });
  await page.getByRole("button", { name: /หมูย่างทดสอบ/ }).click();
  await page.getByRole("button", { name: "รับเงินสดและส่งครัว" }).click();
  await expect(page.getByText("เก็บรายการไว้ในเครื่องแล้ว", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /ใบลูกค้า/ })).toBeVisible();
  await expect(page.getByText(/รายการในเครื่อง: รอส่ง 1/)).toBeVisible();
});

test("branch workspace exposes shift summary, store ordering, and store stock workflows", async ({ page }) => {
  await installSession(page, [
    "takeaway.catalog.view",
    "takeaway.shift.manage",
    "takeaway.central_order.create",
    "takeaway.stock.view",
    "takeaway.stock.manage",
  ], ["branch"]);
  await mockTakeawayApi(page);
  await page.route("**/api/v1/takeaway/shifts", (route) => fulfill(route, [
    { id: "shift-1", status: "open", round_no: 1, business_date: "2026-09-16", opening_cash: "500.00" },
  ]));
  await page.route("**/api/v1/takeaway/shifts/shift-1/summary", (route) => fulfill(route, {
    shift: { id: "shift-1" },
    paid: { order_count: 3, amount: "321.00", tax_amount: "21.00", discount_amount: "0.00" },
    refunded: { order_count: 0, amount: "0.00", tax_amount: "0.00", discount_amount: "0.00" },
    payment_totals: { cash: "321.00" },
    refunded_payments: {},
    expected_cash: "821.00",
    counted_cash: null,
    cash_variance: null,
  }));
  await page.route("**/api/v1/takeaway/catalog/items**", (route) => fulfill(route, []));
  await page.route("**/api/v1/takeaway/central/orders**", (route) => fulfill(route, []));
  await page.route("**/api/v1/takeaway/stock/locations", (route) => fulfill(route, []));
  await page.route("**/api/v1/takeaway/stock/movements**", (route) => fulfill(route, []));
  await page.route("**/api/v1/takeaway/stock**", (route) => fulfill(route, []));

  await page.goto("/takeaway/store/shifts");
  await expect(page.getByText("฿821.00")).toBeVisible();
  await expect(page.getByText("จำนวนบิล")).toBeVisible();

  await page.goto("/takeaway/store/central-orders");
  await expect(page.getByRole("heading", { name: "สั่งสินค้าจากส่วนกลาง" })).toBeVisible();
  await expect(page.getByRole("button", { name: "ใบสั่งประจำ" })).toBeVisible();
  await expect(page.getByRole("button", { name: "ขอสินค้าเพิ่ม" })).toBeVisible();
  await expect(page.getByRole("button", { name: "สินค้านอกแคตตาล็อก" })).toBeVisible();

  await page.goto("/takeaway/store/stock");
  await expect(page.getByRole("heading", { name: "สต๊อกร้านประจำวัน" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "บันทึกความเคลื่อนไหว" })).toBeVisible();
});
