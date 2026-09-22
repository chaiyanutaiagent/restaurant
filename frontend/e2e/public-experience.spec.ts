import { expect, test, type Page, type Route } from "@playwright/test";

const summary = {
  company: {
    id: "11111111-1111-4111-8111-111111111111",
    name: "Foodchain Demo",
    business_slug: "foodchain-demo",
    name_en: null,
    tax_id: null,
    vat_registered: true,
    address: "กรุงเทพฯ",
    phone: "02-000-0000",
    email: null,
    logo_url: null,
    website: null,
    currency: "THB",
    timezone: "Asia/Bangkok",
  },
  featured_products: [],
  branches: [{
    id: "22222222-2222-4222-8222-222222222222",
    code: "BKK",
    name: "สาขากรุงเทพ",
    name_en: null,
    address: "กรุงเทพฯ",
    landmark: "ใกล้สถานี",
    phone: "02-000-0000",
    email: null,
    latitude: 13.7563,
    longitude: 100.5018,
    google_maps_url: null,
    working_hours: null,
    is_active: true,
    is_pickup_available: true,
  }],
  experience: {
    mode: "catalog_locator",
    release_stage: "public_read_only",
    generated_at: new Date().toISOString(),
    stale_after_seconds: 300,
    capabilities: {
      catalog: true,
      branch_locator: true,
      ecommerce: false,
      checkout: false,
      payment: false,
      member_portal: false,
      digital_receipt: false,
    },
    hard_holds: ["owner_ecommerce_mode_decision", "checkout_and_payment_provider"],
  },
};

const product = {
  id: "33333333-3333-4333-8333-333333333333",
  sku: "INTERNAL-SKU",
  barcode: "8850000000000",
  name: "กาแฟซิกเนเจอร์",
  name_en: null,
  description: "เมล็ดกาแฟคั่วสด",
  selling_price: 120,
  vat_type: "included",
  vat_rate: 7,
  category_id: "44444444-4444-4444-8444-444444444444",
  category_name: "เครื่องดื่ม",
  unit_code: "แก้ว",
  image_url: null,
  is_active: true,
  total_qty_available: 5,
  in_stock: true,
};

async function fulfill(route: Route, data: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ data, meta: { version: "test" }, error: null }),
  });
}

async function mockCatalog(page: Page, generatedAt = new Date().toISOString()): Promise<void> {
  await page.route("**/api/public/storefront/businesses/foodchain-demo", (route) => fulfill(route, {
    ...summary,
    experience: { ...summary.experience, generated_at: generatedAt },
  }));
  await page.route("**/api/public/storefront/businesses/foodchain-demo/products**", (route) => fulfill(route, [product]));
}

test("catalog and branch locator disclose that checkout and payment are closed", async ({ page }) => {
  await mockCatalog(page);
  await page.goto("/foodchain-demo");

  await expect(page.getByRole("heading", { name: "Foodchain Demo" })).toBeVisible();
  await expect(page.getByTestId("catalog-only-notice")).toContainText("ยังไม่เปิดตะกร้า สั่งซื้อ ชำระเงิน");
  await expect(page.getByTestId("public-capability-status")).toContainText("เปิดใช้ · แคตตาล็อก");
  await expect(page.getByTestId("public-capability-status")).toContainText("ยังไม่เปิด · สั่งซื้อ");
  await expect(page.getByText("กาแฟซิกเนเจอร์", { exact: true })).toBeVisible();
  await expect(page.getByText("INTERNAL-SKU", { exact: false })).toHaveCount(0);
  await expect(page.getByText("8850000000000", { exact: false })).toHaveCount(0);
  await expect(page.getByText("สาขากรุงเทพ", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "สำหรับพนักงาน" }).first()).toHaveAttribute("href", "/foodchain-demo/admin");
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});

test("stale public data is visible but clearly warned", async ({ page }) => {
  await mockCatalog(page, "2020-01-01T00:00:00Z");
  await page.goto("/foodchain-demo");
  await expect(page.getByText("ข้อมูลอาจล่าช้า", { exact: true })).toBeVisible();
  await expect(page.getByText("กาแฟซิกเนเจอร์", { exact: true })).toBeVisible();
});

test("failed public summary never renders a false catalog success", async ({ page }) => {
  await page.route("**/api/public/storefront/businesses/foodchain-demo", (route) => route.fulfill({
    status: 429,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Too many requests; try again later" }),
  }));
  await page.route("**/api/public/storefront/businesses/foodchain-demo/products**", (route) => fulfill(route, []));
  await page.goto("/foodchain-demo");
  await expect(page.locator('[data-system-state="error"]')).toBeVisible();
  await expect(page.getByTestId("catalog-only-notice")).toHaveCount(0);
});
