import { test, expect, type Page } from "@playwright/test";

const company = "11111111-1111-4111-8111-111111111111";
const branch = "22222222-2222-4222-8222-222222222222";
async function mockApi(page: Page, forceWrongProduct = false) {
  await page.route("https://*.foodchainservice.com/api/v1/**", async (route) => {
    const req = route.request(), url = new URL(req.url());
    let data: unknown = [];
    if (url.pathname.includes("/mobile-store/businesses/")) data = { business_code: "sample-co", name: "Test Company" };
    else if (url.pathname.endsWith("/mobile-pos/branches")) data = [{ id: branch, code: "TEST-01", name: "Test branch" }];
    else if (url.pathname.endsWith("/mobile-pos/login")) {
      const body = req.postDataJSON();
      const user = { id: "store-user", company_id: company, username: "stock", display_name: "Test Staff", is_superuser: false };
      const product = forceWrongProduct ? "retail_pos" : body.product;
      const claims = { sub: user.id, company_id: company, branch_id: branch, brand_id: "brand-test", station_key: body.station_key,
        client_surface: product === "takeaway" ? "takeaway_store" : product === "restaurant" ? "restaurant_pos" : "retail_pos",
        store_device_id: body.device_id, business_type: product, target_database: product,
        permissions: product === "takeaway" ? ["takeaway.store.access", "takeaway.stock.view"] : ["pos.sale.view", "pos.sale.create", "pos.draft.view", "inventory.product.view", "inventory.stock.view", ...(product === "restaurant" ? ["fb.menu.view", "fb.table.manage", "fb.order.create"] : [])], exp: Math.floor(Date.now()/1000)+3600 };
      data = { user, business_slug: "sample-co", access_token: `test.${Buffer.from(JSON.stringify(claims)).toString("base64url")}.fixture`, refresh_token: "test-refresh" };
    } else if (url.pathname.endsWith("/takeaway/status")) data = { company_id: company, branch_id: branch, brand_id: "brand-test", enabled: true, writes_enabled: false, hard_holds: [] };
    else if (url.pathname.endsWith("/mobile-pos/context")) data = [{ branch_id: branch, branch_code: "TEST-01", branch_name: "Test branch", is_default: true, role_name: "POS" }];
    else if (url.pathname.endsWith("/stock/locations")) data = [{ id: "66666666-6666-4666-8666-666666666666", company_id: company, branch_id: branch, code: "SHOP", name: "หน้าร้าน", is_active: true }];
    else if (url.pathname.endsWith("/pos/shifts/current")) data = { id: "shift-test", shift_number: "RS-TEST", shift_type: "staff_cashier", version: 1, status: "open", branch_id: branch, location_id: "66666666-6666-4666-8666-666666666666", user_id: "store-user", opened_at: "2026-10-04T08:00:00Z", opening_cash: 1000, total_sales: 0, total_orders: 0, total_voids: 0 };
    else if (url.pathname.endsWith("/settings")) data = { branch_id: branch, pos_require_customer: false, pos_allow_discount: true, pos_max_discount_pct: 20, receipt_copies: 1, allow_negative_stock: false, fb_service_mode: "full_service", fb_qs_qr_token: null };
    else if (url.pathname.endsWith("/products/retail/lookup")) data = { status: "not_found", product: null, stock: null, reason_code: "not_found" };
    return route.fulfill({ json: { data, meta: {}, error: null } });
  });
}
async function login(page: Page, product = "takeaway") {
  await page.goto(`/connect/${product}`);
  await page.getByLabel("Business Code", { exact: true }).fill("sample-co");
  await page.getByRole("button", { name: "ตรวจสอบบริษัท", exact: true }).click();
  await page.getByLabel("ชื่อผู้ใช้", { exact: true }).fill("stock");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "ตรวจสอบบัญชีและสาขา", exact: true }).click();
  await page.getByRole("button", { name: "เข้าใช้งานสาขานี้", exact: true }).click();
  await expect(page).toHaveURL(product === "takeaway" ? /\/takeaway\/store\/stock$/ : product === "restaurant" ? /\/restaurant\/pos$/ : /\/retail\/pos$/);
}

test("three-product launcher fits tablet and phone", async ({ page }) => {
  for (const viewport of [{ width: 1024, height: 768 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport); await page.goto("/");
    await expect(page.getByRole("heading", { name: "เลือกระบบหน้าร้าน" })).toBeVisible();
    for (const name of ["Takeaway", "Restaurant", "Retail"]) await expect(page.getByRole("link", { name: `เข้าใช้ ${name}` })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.screenshot({ path: "test-results/mobile-pos/launcher-phone.png", fullPage: true });
});

test("onboarding retains branch-scoped permissions and cannot enter other products or admin", async ({ page }) => {
  const requests: string[] = []; page.on("request", (req) => requests.push(req.url()));
  await mockApi(page); await login(page);
  await expect(page.getByRole("link", { name: "ขายและเตรียมสินค้า", exact: true })).toHaveCount(0);
  await page.goto("/takeaway/store/orders");
  await expect(page.getByRole("alert")).toHaveText("ไม่มีสิทธิ์ใช้งานหน้านี้");
  for (const path of ["/restaurant/pos", "/retail/pos", "/platform", "/takeaway/central/orders"]) {
    await page.goto(path); await expect(page.getByRole("heading", { name: "ไม่อนุญาตให้เข้าหน้านี้" })).toBeVisible();
  }
  expect(requests.some((url) => url.includes("auto-login") || url.includes("downloads/takeaway-store"))).toBe(false);
});

test("restore opens assigned store and logout returns to launcher without the legacy updater", async ({ page }) => {
  await mockApi(page); await login(page); await page.goto("/");
  await expect(page).toHaveURL(/\/takeaway\/store\/stock$/);
  await page.getByRole("link", { name: "เครื่องพิมพ์/แอป", exact: true }).click();
  await expect(page.getByRole("heading", { name: "อุปกรณ์ Foodchainservice POS" })).toBeVisible();
  await expect(page.getByText("ไม่รองรับการพิมพ์โดยตรงในโหมดนี้", { exact: false })).toBeVisible();
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "ออกจากระบบ / เปลี่ยนบริษัท", exact: true }).click();
  await expect(page.getByRole("heading", { name: "เลือกระบบหน้าร้าน" })).toBeVisible();
  await page.reload(); await expect(page.getByRole("heading", { name: "เลือกระบบหน้าร้าน" })).toBeVisible();
});

test("offline indicator does not claim backend connectivity", async ({ page, context }) => {
  await page.goto("/"); await expect(page.getByRole("heading", { name: "เลือกระบบหน้าร้าน" })).toBeVisible();
  await context.setOffline(true); await expect(page.getByRole("status").filter({ hasText: "ออฟไลน์" })).toBeVisible();
  await context.setOffline(false); await expect(page.getByRole("status").filter({ hasText: "ไม่ใช่การยืนยันสถานะเซิร์ฟเวอร์" })).toBeVisible();
});

for (const product of ["restaurant", "retail_pos"] as const) {
  test(`${product} loads the actual POS with scoped headers and rejects the other product`, async ({ page }) => {
    const errors: string[] = []; page.on("pageerror", (error) => errors.push(error.message));
    await mockApi(page);
    const catalog = page.waitForRequest((req) => new URL(req.url()).pathname.endsWith("/api/v1/products"));
    await login(page, product);
    await expect(page.getByRole("navigation", { name: product === "restaurant" ? "พื้นที่ทำงาน POS" : "พื้นที่ทำงาน Retail POS", exact: true })).toBeVisible();
    const req = await catalog;
    expect(new URL(req.url()).host).toBe(`uat-${product === "restaurant" ? "restaurant" : "retail"}.foodchainservice.com`);
    expect(new URL(req.url()).searchParams.get("catalog_scope")).toBe(product === "restaurant" ? "restaurant_menu" : "retail_sale");
    expect(req.headers()["x-company-id"]).toBe(company); expect(req.headers()["x-branch-id"]).toBe(branch);
    expect(req.headers()["x-store-device-id"]).toBeTruthy();
    if (product === "restaurant") {
      await page.getByRole("button", { name: "โต๊ะ + QR", exact: true }).click();
      await expect(page.getByRole("heading", { name: /โต๊ะ/ }).first()).toBeVisible();
    } else {
      const lookup = page.waitForRequest((request) => request.url().includes("/products/retail/lookup"));
      const search = page.getByPlaceholder("สแกนบาร์โค้ด / ค้นหาชื่อ / SKU");
      await search.fill("8850000000001"); await search.press("Enter");
      expect(new URL((await lookup).url()).searchParams.get("location_id")).toBe("66666666-6666-4666-8666-666666666666");
      await expect(page.getByText("ไม่พบบาร์โค้ด", { exact: true })).toBeVisible();
    }
    await page.screenshot({ path: `test-results/mobile-pos/${product}-tablet.png`, fullPage: true });
    await page.goto(product === "restaurant" ? "/retail/pos" : "/restaurant/tables");
    await expect(page.getByRole("heading", { name: "ไม่อนุญาตให้เข้าหน้านี้" })).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test("a mismatched product response never establishes a session", async ({ page }) => {
  await mockApi(page, true); await page.goto("/connect/takeaway");
  await page.getByLabel("Business Code", { exact: true }).fill("sample-co");
  await page.getByRole("button", { name: "ตรวจสอบบริษัท", exact: true }).click();
  await page.getByLabel("ชื่อผู้ใช้", { exact: true }).fill("stock");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "ตรวจสอบบัญชีและสาขา", exact: true }).click();
  await page.getByRole("button", { name: "เข้าใช้งานสาขานี้", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("ไม่ตรงกับระบบที่เลือก");
  await page.goto("/"); await expect(page.getByRole("heading", { name: "เลือกระบบหน้าร้าน" })).toBeVisible();
});

test("an in-flight native write blocks logout before clearing local data", async ({ page }) => {
  await mockApi(page); await login(page);
  await page.evaluate(async () => {
    const path = "/src/lib/nativePosWorkGuard.ts";
    const guard = await import(/* @vite-ignore */ path); guard.beginNativeWrite("sale-in-flight");
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "ออกจากระบบ / เปลี่ยนบริษัท", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("กำลังบันทึกหรือยืนยันรายการ");
  await expect(page).toHaveURL(/\/takeaway\/store\/stock$/);
});

test("a pending sale prevents logout or company switching even after session loss", async ({ page }) => {
  await mockApi(page); await login(page);
  await page.evaluate(async () => {
    const dbPath = "/src/mobile-pos/storeDb.ts";
    const { db } = await import(/* @vite-ignore */ dbPath);
    await db.takeawayPendingSales.put({ client_sale_id: "pending-fixture", status: "pending" });
  });
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "ออกจากระบบ / เปลี่ยนบริษัท", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("รายการค้างส่ง");
  await expect(page.getByRole("heading", { name: "เลือกระบบหน้าร้าน" })).toHaveCount(0);
  await page.evaluate(async () => {
    const sessionPath = "/src/mobile-pos/session.ts";
    const { clearSession } = await import(/* @vite-ignore */ sessionPath); await clearSession();
  });
  await page.goto("/connect/retail_pos");
  await page.getByLabel("Business Code", { exact: true }).fill("sample-co");
  await page.getByRole("button", { name: "ตรวจสอบบริษัท", exact: true }).click();
  await page.getByLabel("ชื่อผู้ใช้", { exact: true }).fill("stock");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("fixture-password");
  await page.getByRole("button", { name: "ตรวจสอบบัญชีและสาขา", exact: true }).click();
  await page.getByRole("button", { name: "เข้าใช้งานสาขานี้", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("รายการค้างส่ง");
  expect(await page.evaluate(async () => {
    const dbPath = "/src/mobile-pos/storeDb.ts";
    const { db } = await import(/* @vite-ignore */ dbPath); return db.takeawayPendingSales.count();
  })).toBe(1);
});
