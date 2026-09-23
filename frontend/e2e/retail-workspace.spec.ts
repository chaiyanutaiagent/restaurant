import { expect, test, type Page, type Route } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const brandId = "22222222-2222-4222-8222-222222222222";
const branchId = "33333333-3333-4333-8333-333333333333";
const userId = "55555555-5555-4555-8555-555555555555";
const locationId = "66666666-6666-4666-8666-666666666666";
const shiftId = "77777777-7777-4777-8777-777777777777";
const permissions = [
  "pos.sale.view",
  "pos.sale.create",
  "pos.draft.view",
  "pos.draft.create",
  "pos.refund.view",
  "system.device.view",
];

function response(data: unknown, meta: Record<string, unknown> = {}): string {
  return JSON.stringify({ data, meta: { version: "test", ...meta }, error: null });
}

async function fulfill(route: Route, data: unknown, meta: Record<string, unknown> = {}, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", body: response(data, meta) });
}

async function installRetailSession(page: Page): Promise<void> {
  const payload = {
    permissions,
    scope_types: ["company", "branch"],
    company_id: companyId,
    branch_id: branchId,
    brand_id: brandId,
    business_type: "retail_pos",
    target_database: "retail_pos",
  };
  const token = `header.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.signature`;
  await page.addInitScript(({ accessToken, catalogKey, company, brand, branch, user, userPermissions }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({ state: {
      accessToken,
      refreshToken: "test-refresh",
      companyId: company,
      branchId: branch,
      brandId: brand,
      businessSlug: "foodchain-retail-uat",
      businessType: "retail_pos",
      targetDatabase: "retail_pos",
      scopeTypes: ["company", "branch"],
      stationKey: null,
      permissions: userPermissions,
      user: {
        id: user,
        company_id: company,
        username: "retail-cashier",
        email: "retail@example.com",
        phone: null,
        first_name: null,
        last_name: null,
        display_name: "Retail Cashier",
        is_active: true,
        is_superuser: false,
        last_login_at: null,
      },
    }, version: 0 }));
    window.localStorage.setItem("pos-catalog-isolation-key", catalogKey);
  }, {
    accessToken: token,
    catalogKey: `${companyId}:${brandId}:${branchId}:retail_pos:retail_sale`,
    company: companyId,
    brand: brandId,
    branch: branchId,
    user: userId,
    userPermissions: permissions,
  });
}

async function mockRetailApis(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/my-branches")) {
      return fulfill(route, [{ id: branchId, code: "BKK", name: "Retail UAT", brand_id: brandId }]);
    }
    if (path.endsWith("/stock/locations")) {
      return fulfill(route, [{ id: locationId, company_id: companyId, branch_id: branchId, code: "SHOP", name: "หน้าร้าน", description: null, is_active: true }]);
    }
    if (path.endsWith("/pos/shifts/current")) {
      return fulfill(route, {
        id: shiftId,
        shift_number: "RS20260923-001",
        shift_type: "staff_cashier",
        version: 1,
        status: "open",
        branch_id: branchId,
        location_id: locationId,
        user_id: userId,
        opened_at: "2026-09-23T08:00:00Z",
        closed_at: null,
        opening_cash: 1000,
        closing_cash: null,
        expected_cash: null,
        cash_difference: null,
        total_sales: 0,
        total_orders: 0,
        total_voids: 0,
        close_reason_code: null,
        cash_count_json: null,
        opened_device_id: null,
        opened_device_code: null,
        closed_device_id: null,
        closed_device_code: null,
        closed_by_user_id: null,
        close_snapshot_json: null,
      });
    }
    if (path.includes(`/system/branches/${branchId}/settings`)) {
      return fulfill(route, {
        id: "88888888-8888-4888-8888-888888888888",
        branch_id: branchId,
        pos_require_customer: false,
        pos_allow_discount: true,
        pos_max_discount_pct: 20,
        pos_cashier_discount_limit_pct: 10,
        pos_price_override_auto_limit_pct: 0,
        pos_price_override_auto_limit_amount: 0,
        pos_price_override_max_deviation_pct: 0,
        pos_price_override_min_margin_pct: 0,
        pos_price_override_self_approval: false,
        pos_hold_draft_ttl_minutes: 120,
        receipt_copies: 1,
        allow_negative_stock: false,
      });
    }
    if (path.endsWith("/products/retail/lookup")) {
      return fulfill(route, { status: "not_found", product: null, stock: null, reason_code: "not_found" });
    }
    if (path.endsWith("/products")) return fulfill(route, [], { total: 0, page: 1, limit: 100 });
    if (path.endsWith("/categories") || path.endsWith("/units") || path.endsWith("/stock/balances") || path.endsWith("/pos/drafts") || path.endsWith("/pos/sales") || path.endsWith("/system/branches/replacement-rules")) {
      return fulfill(route, []);
    }
    if (path.endsWith("/crm/settings")) return fulfill(route, {});
    return fulfill(route, []);
  });
}

test.beforeEach(async ({ page }) => {
  await installRetailSession(page);
  await mockRetailApis(page);
});

test("Retail workspace stays server-authoritative and usable on desktop and tablet", async ({ page }) => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 820, height: 1180 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/retail/pos");
    await expect(page.getByText("Retail POS", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Pilot · Production ใช้ Legacy/)).toBeVisible();
    await expect(page.getByText(/Retail Scan-first · Pilot/)).toBeVisible();
    await expect(page.getByText(/signed Company \/ Brand \/ Branch/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }

  const lookup = page.waitForRequest((request) => request.url().includes("/api/v1/products/retail/lookup"));
  const search = page.getByPlaceholder("สแกนบาร์โค้ด / ค้นหาชื่อ / SKU");
  await search.fill("8850000000001");
  await search.press("Enter");
  const lookupRequest = await lookup;
  expect(new URL(lookupRequest.url()).searchParams.get("location_id")).toBe(locationId);
  await expect(page.getByText("ไม่พบบาร์โค้ด", { exact: true })).toBeVisible();
});
