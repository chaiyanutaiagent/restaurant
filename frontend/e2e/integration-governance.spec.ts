import { expect, test, type Page, type Route } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const userId = "55555555-5555-4555-8555-555555555555";
const keyId = "66666666-6666-4666-8666-666666666666";
const webhookId = "77777777-7777-4777-8777-777777777777";
const orderId = "88888888-8888-4888-8888-888888888888";

function response(data: unknown): string {
  return JSON.stringify({ data, meta: { version: "test" }, error: null });
}

async function fulfill(route: Route, data: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", body: status >= 400 ? JSON.stringify({ detail: "Permission denied" }) : response(data) });
}

async function installSession(page: Page): Promise<void> {
  const payload = { permissions: ["system.company.edit", "pos.sale.view", "pos.sale.create"], scope_types: ["company"], branch_id: null };
  const token = `header.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.signature`;
  await page.addInitScript(({ accessToken, company, user }) => window.localStorage.setItem("erp-auth", JSON.stringify({ state: {
    accessToken, refreshToken: "test-refresh", companyId: company, branchId: null, brandId: null, businessSlug: "foodchain-test",
    businessType: null, targetDatabase: null, scopeTypes: ["company"], stationKey: null,
    permissions: ["system.company.edit", "pos.sale.view", "pos.sale.create"],
    user: { id: user, company_id: company, username: "owner", email: "owner@example.com", phone: null, first_name: null, last_name: null, display_name: "Owner", is_active: true, is_superuser: false, last_login_at: null },
  }, version: 0 })), { accessToken: token, company: companyId, user: userId });
}

async function mockIntegration(page: Page, options: { status?: number; delay?: number; empty?: boolean } = {}): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    if (options.delay) await new Promise((resolve) => setTimeout(resolve, options.delay));
    if (options.status) return fulfill(route, null, options.status);
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/integrations/api-keys")) return fulfill(route, options.empty ? [] : [{ id: keyId, company_id: companyId, name: "Storefront", purpose: "Catalog sync", owner_contact: "ops@example.com", key_prefix: "ABCDEF12", scopes: ["products:read"], is_active: true, last_used_at: null, expires_at: "2026-12-31T23:59:59Z", created_at: "2026-09-23T08:00:00Z", revoked_at: null, rotated_from_id: null }]);
    if (path.endsWith("/integrations/webhooks")) return fulfill(route, options.empty ? [] : [{ id: webhookId, company_id: companyId, name: "Order Events", url: "https://partner.example/webhook", events: ["order.received"], secret_configured: true, secret_rotated_at: "2026-09-23T08:00:00Z", incoming_source: "partner-shop", is_active: true, last_triggered_at: null, failure_count: 0, created_at: "2026-09-23T08:00:00Z" }]);
    if (path.endsWith("/integrations/external-orders")) return fulfill(route, options.empty ? [] : [{ id: orderId, source: "partner-shop", external_order_id: "EXT-001", status: "needs_review", customer_name: "UAT Customer", customer_phone: null, total_amount: 1, server_total_amount: 125, review_reasons: ["price_mismatch:WP65-ITEM"], payment_status: "paid", sale_order_id: null, received_at: "2026-09-23T08:00:00Z", processed_at: null, reviewed_at: null, reviewed_by: null }]);
    if (path.endsWith(`/integrations/external-orders/${orderId}/review`)) return fulfill(route, { status: "accepted" });
    return fulfill(route, []);
  });
}

test.beforeEach(async ({ page }) => installSession(page));

test("desktop and tablet expose owned expiring keys, encrypted webhook posture and server order review", async ({ page }) => {
  await mockIntegration(page);
  for (const viewport of [{ width: 1440, height: 900 }, { width: 820, height: 1180 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/integrations");
    await expect(page.getByText("ops@example.com", { exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "Webhooks" }).click();
    await expect(page.getByText(/เข้ารหัส/)).toBeVisible();
    await expect(page.getByText("partner-shop", { exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "ออร์เดอร์จากเว็บ" }).click();
    await expect(page.getByText("รอตรวจ", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/฿125/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }
  const review = page.waitForRequest((request) => request.url().endsWith(`/api/v1/integrations/external-orders/${orderId}/review`));
  page.once("dialog", (dialog) => dialog.accept("ตรวจแล้วใช้ราคา Server"));
  await page.getByRole("button", { name: "ยอมรับราคา Server" }).click();
  expect((await review).postDataJSON()).toEqual({ decision: "accept", reason: "ตรวจแล้วใช้ราคา Server" });
});

test("loading, empty and permission-denied remain explicit", async ({ page }) => {
  await mockIntegration(page, { delay: 400 });
  await page.goto("/integrations");
  await expect(page.locator('[data-system-state="loading"]')).toBeVisible();
  await expect(page.getByText("Storefront", { exact: true })).toBeVisible();

  await page.unrouteAll({ behavior: "wait" });
  await mockIntegration(page, { empty: true });
  await page.reload();
  await expect(page.locator('[data-system-state="empty"]').first()).toBeVisible();

  await page.unrouteAll({ behavior: "wait" });
  await mockIntegration(page, { status: 403 });
  await page.reload();
  await expect(page.locator('[data-system-state="permission_denied"]')).toBeVisible();
});
