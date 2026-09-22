import { expect, test, type Page, type Route } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const brandId = "22222222-2222-4222-8222-222222222222";
const branchId = "33333333-3333-4333-8333-333333333333";
const secondBranchId = "44444444-4444-4444-8444-444444444444";
const userId = "55555555-5555-4555-8555-555555555555";
const permissions = [
  "system.company.edit",
  "system.branch.view",
  "system.user.view",
  "system.role.view",
  "system.device.view",
  "company.kitchen.view",
  "pos.sale.view",
  "fb.kitchen.ticket.manage",
];

const modules = [
  ["erp", "production", true, ["view", "export"], "platform_core"],
  ["central_kitchen", "read_only", true, ["view"], "restaurant"],
  ["restaurant_pos", "pilot", true, ["view", "create"], "restaurant"],
  ["takeaway_pos", "dark_launch", true, [], "takeaway"],
  ["retail_pos", "legacy", true, ["view"], "retail"],
  ["hotel_pms", "planned", false, [], "platform_core"],
].map(([module_key, readiness, user_permitted, allowed_actions, data_source]) => ({
  module_key,
  lifecycle: readiness === "planned" ? "planned" : readiness === "dark_launch" ? "dark_launch" : "active",
  readiness,
  environment: "uat",
  company_enabled: readiness !== "planned",
  plan_included: readiness !== "planned",
  runtime_ready: readiness !== "planned",
  user_permitted,
  effective_access: Boolean(user_permitted) && readiness !== "planned",
  reason_code: readiness === "planned" ? "lifecycle_planned" : "enabled",
  allowed_actions,
  enabled_branch_ids: [branchId],
  branch_scope: "all",
  feature_flags: {},
  data_source,
  status_reason: readiness === "dark_launch" ? "เปิดให้ตรวจข้อมูล แต่ยังปิดธุรกรรม" : null,
  updated_at: "2026-09-20T08:00:00Z",
  updated_by: userId,
  audit_id: null,
}));

const context = {
  contract_version: "2026-09-19.1",
  environment: "uat",
  company: { id: companyId, code: "FCS", name: "Foodchain Test Company" },
  brand: { id: brandId, code: "BRAND", name: "Test Brand" },
  branch: { id: branchId, code: "BKK", name: "สาขากรุงเทพ" },
  station_or_device_id: "POS-01",
  business_type: "restaurant",
  target_database: "restaurant",
  timezone: "Asia/Bangkok",
  currency: "THB",
  tax: { scope: "company", configured: true, vat_registered: true, tax_id: "0100000000000", tax_branch_code: "00000", price_vat_type: "inclusive", vat_rate: 7 },
  all_scope_allowed: { brand: true, branch: true, station: false },
  transport: { authoritative_source: "signed_token", company_header: "X-Company-ID", branch_header: "X-Branch-ID", client_context_is_trusted: false, switch_requires_new_token: true },
  updated_at: "2026-09-20T08:00:00Z",
};

const workItem = {
  id: "device:pos-01",
  type: "device_sync",
  source_app: "restaurant_pos",
  severity: "blocker",
  title: "เครื่องขาย POS-01 รอซิงก์",
  company_id: companyId,
  brand_id: brandId,
  branch_id: branchId,
  owner_id: null,
  due_at: "2026-09-20T09:00:00Z",
  status: "open",
  permission_required: "system.device.view",
  available_actions: ["assign", "acknowledge", "dismiss"],
  deep_link: "/devices",
  unread: true,
  business_impact: 90,
  created_at: "2026-09-20T07:00:00Z",
  updated_at: "2026-09-20T08:00:00Z",
};

const overview = {
  contract_version: "2026-09-19.1",
  context,
  task_summary: { total: 1, unread: 1, blocker: 1, error: 0, warning: 0 },
  sections: modules.filter((module) => module.module_key !== "hotel_pms").map((module, index) => ({
    module_key: module.module_key,
    title: String(module.module_key).replaceAll("_", " "),
    readiness: module.readiness,
    data_source: module.data_source,
    status: index === 0 ? "stale" : index === 1 ? "pending_sync" : "online",
    metrics: [{ key: "total", label: "รายการ", value: index + 1, severity: "info", deep_link: null }],
    updated_at: "2026-09-20T08:00:00Z",
    stale: index === 0,
    error_code: null,
  })),
  generated_at: "2026-09-20T08:00:00Z",
};

const governance = {
  contract_version: "2026-09-23.1",
  company_id: companyId,
  branch_id: null,
  scope: "company",
  environment: "uat",
  release_commit: "wp65-local",
  production_authorized: false,
  areas: [
    { key: "api_webhook_governance", title: "API Key และ Webhook", state: "attention", mode: "read_only", source_system: "legacy.integration", reason: "พบ delivery รอลองใหม่", deep_link: "/integrations", metrics: [{ key: "retry_pending", label: "รอลองใหม่", value: 1, severity: "warning" }], updated_at: "2026-09-23T08:00:00Z", stale: false },
    { key: "incident_management", title: "Incident Management", state: "planned", mode: "planned", source_system: "no_tenant_incident_contract", reason: "ยังไม่มีสัญญาข้อมูล จึงไม่มี action ปลอม", deep_link: null, metrics: [], updated_at: null, stale: false },
  ],
  release_gates: [
    { key: "software_uat", title: "Software UAT", state: "pass", server_enforced: true, reason: "มีหลักฐาน software gate", evidence_reference: "docs/scopes/BATCH-C-PHASE-GATE-03.md" },
    { key: "production", title: "Production activation", state: "hold", server_enforced: true, reason: "WP65 อนุญาตเฉพาะ Local/UAT", evidence_reference: null },
  ],
  coverage: [
    { key: "restaurant", title: "Restaurant POS", state: "available", entry_route: "/restaurant", release_boundary: "Software UAT passed; physical acceptance remains HOLD" },
    { key: "retail", title: "Retail POS", state: "hold", entry_route: "/pos", release_boundary: "Cash Pilot only" },
    { key: "integration_reporting", title: "Integration & Reporting", state: "read_only", entry_route: "/company/governance", release_boundary: "Server evidence only" },
  ],
  summary: { ready: 0, attention: 1, blocked: 0, hold: 1, planned: 1 },
  stale_after_seconds: 300,
  generated_at: "2026-09-23T08:00:00Z",
};

type MockOptions = {
  emptyActions?: boolean;
  overviewStatus?: number;
  overviewDelay?: number;
};

function apiResponse(data: unknown): Record<string, unknown> {
  return { data, meta: { version: "test", contract_version: "2026-09-19.1" }, error: null };
}

async function fulfill(route: Route, data: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(status >= 400 ? { detail: "Permission denied" } : apiResponse(data)) });
}

async function installSession(page: Page): Promise<void> {
  const payload = { permissions, scope_types: ["company", "branch"], branch_id: branchId, brand_id: brandId, business_type: "restaurant", target_database: "restaurant", station_key: null };
  const token = `header.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.signature`;
  await page.addInitScript(({ accessToken, company, branch, brand, userPermissions }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({ state: {
      accessToken,
      refreshToken: "test-refresh-token",
      user: { id: "55555555-5555-4555-8555-555555555555", company_id: company, username: "company.owner", email: "owner@example.com", phone: null, first_name: null, last_name: null, display_name: "Company Owner", is_active: true, is_superuser: false, last_login_at: null },
      companyId: company,
      businessSlug: "foodchain-test",
      brandId: brand,
      branchId: branch,
      businessType: "restaurant",
      targetDatabase: "restaurant",
      scopeTypes: ["company", "branch"],
      stationKey: null,
      permissions: userPermissions,
    }, version: 0 }));
  }, { accessToken: token, company: companyId, branch: branchId, brand: brandId, userPermissions: permissions });
}

async function mockCompanyApi(page: Page, options: MockOptions = {}): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/company/context")) return fulfill(route, context);
    if (path.endsWith("/company/access")) return fulfill(route, { contract_version: "2026-09-19.1", company_id: companyId, user_id: userId, scope_types: ["company", "branch"], assignment_ids: [], permissions, default_route: "/company", modules });
    if (path.endsWith("/company/action-center") && route.request().method() === "GET") return fulfill(route, { contract_version: "2026-09-19.1", items: options.emptyActions ? [] : [workItem], total: options.emptyActions ? 0 : 1, unread: options.emptyActions ? 0 : 1, generated_at: "2026-09-20T08:00:00Z" });
    if (/\/company\/action-center\/[^/]+\/actions$/.test(path)) return fulfill(route, { ...workItem, owner_id: userId });
    if (path.endsWith("/company/overview")) {
      if (options.overviewDelay) await new Promise((resolve) => setTimeout(resolve, options.overviewDelay));
      return fulfill(route, overview, options.overviewStatus ?? 200);
    }
    if (path.endsWith("/company/operational-status")) return fulfill(route, {
      contract_version: "2026-09-19.1",
      components: [
        { id: "pos-01", component_type: "pos", name: "POS-01", state: "pending_sync", company_id: companyId, branch_id: branchId, station_key: null, last_seen_at: "2026-09-20T08:00:00Z", last_sync_at: "2026-09-20T07:55:00Z", queue_size: 4, error_code: null, retryable: true, source_system: "restaurant", updated_at: "2026-09-20T08:00:00Z" },
        { id: "kds-01", component_type: "kds", name: "KDS-01", state: "degraded", company_id: companyId, branch_id: branchId, station_key: null, last_seen_at: "2026-09-20T07:50:00Z", last_sync_at: null, queue_size: 0, error_code: "SLOW_HEARTBEAT", retryable: false, source_system: "restaurant", updated_at: "2026-09-20T08:00:00Z" },
      ],
      summary: { online: 0, offline: 0, degraded: 1, pending_sync: 1, stale: 0, error: 0, disabled: 0 },
      generated_at: "2026-09-20T08:00:00Z",
    });
    if (path.endsWith("/company/governance")) return fulfill(route, governance);
    if (path.endsWith("/system/me/branches")) return fulfill(route, [
      { branch_id: branchId, branch_name: "สาขากรุงเทพ", branch_code: "BKK", brand_id: brandId, business_type: "restaurant", target_database: "restaurant", role_name: "Owner", is_default: true, station_key: null },
      { branch_id: secondBranchId, branch_name: "สาขาเชียงใหม่", branch_code: "CNX", brand_id: brandId, business_type: "restaurant", target_database: "restaurant", role_name: "Owner", is_default: false, station_key: null },
    ]);
    if (path.endsWith("/auth/switch-branch")) {
      const switchedPayload = { permissions, scope_types: ["branch"], branch_id: secondBranchId, brand_id: brandId, business_type: "restaurant", target_database: "restaurant", station_key: null };
      return fulfill(route, { access_token: `header.${Buffer.from(JSON.stringify(switchedPayload)).toString("base64url")}.signature`, refresh_token: "switched-refresh-token", token_type: "bearer", expires_in: 900, business_slug: "foodchain-test", user: { id: userId, company_id: companyId, username: "company.owner", email: "owner@example.com", phone: null, first_name: null, last_name: null, display_name: "Company Owner", is_active: true, is_superuser: false, last_login_at: null } });
    }
    return fulfill(route, []);
  });
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
}

test.beforeEach(async ({ page }) => {
  await installSession(page);
});

test("desktop dashboard renders company context, readiness, stale and sync states", async ({ page }) => {
  await mockCompanyApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/company");

  await expect(page.getByTestId("company-shell")).toBeVisible();
  await expect(page.getByText("UAT", { exact: true })).toBeVisible();
  await expect(page.getByTestId("company-context-switcher")).toContainText("Foodchain Test Company");
  await expect(page.getByText("ข้อมูลเก่า", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("รอซิงก์", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("ต้องตรวจสอบ", { exact: true }).first()).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByText("ข้ามไปเนื้อหาหลัก", { exact: true })).toBeFocused();
  await expectNoHorizontalOverflow(page);
});

test("tablet launcher blocks dark launch, labels read-only and excludes planned Hotel", async ({ page }) => {
  await mockCompanyApi(page);
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/company/apps");

  await expect(page.getByRole("heading", { name: "แอปทั้งหมด" })).toBeVisible();
  await expect(page.getByText("Dark launch", { exact: true })).toBeVisible();
  await expect(page.getByText("ดูข้อมูลเท่านั้น", { exact: true })).toBeVisible();
  await expect(page.getByText("Hotel PMS", { exact: true })).toHaveCount(0);
  await expect(page.locator('a[href="/takeaway"]')).toHaveCount(0);
  const undersizedButtons = await page.locator("button").evaluateAll((buttons) => buttons.filter((button) => {
    const rect = button.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && (rect.width < 44 || rect.height < 44);
  }).length);
  expect(undersizedButtons).toBe(0);
  await expectNoHorizontalOverflow(page);
});

test("Action Center shows supported actions and posts an audited self assignment", async ({ page }) => {
  await mockCompanyApi(page);
  const actionRequest = page.waitForRequest((request) => /\/company\/action-center\/[^/]+\/actions$/.test(new URL(request.url()).pathname));
  await page.goto("/company/actions");
  await page.getByRole("button", { name: "รับผิดชอบ" }).click();
  const request = await actionRequest;
  const payload = request.postDataJSON() as { action: string; reason: string; owner_id: string };
  expect(payload.action).toBe("assign");
  expect(payload.owner_id).toBe(userId);
  expect(payload.reason).toContain("Company Action Center");
  await expect(page.getByText("รับผิดชอบรายการแล้ว", { exact: true })).toBeVisible();
});

test("loading, empty, offline and permission-denied states remain explicit", async ({ page, context: browserContext }) => {
  await mockCompanyApi(page, { overviewDelay: 500 });
  await page.goto("/company");
  await expect(page.getByTestId("company-dashboard-loading")).toBeVisible();
  await expect(page.getByTestId("company-dashboard")).toBeVisible();

  await browserContext.setOffline(true);
  await expect(page.getByTestId("company-offline-banner")).toBeVisible();
  await browserContext.setOffline(false);

  await page.unrouteAll({ behavior: "wait" });
  await mockCompanyApi(page, { emptyActions: true });
  await page.goto("/company/actions");
  await expect(page.locator('[data-system-state="empty"]')).toBeVisible();

  await page.unrouteAll({ behavior: "wait" });
  await mockCompanyApi(page, { overviewStatus: 403 });
  await page.goto("/company");
  await expect(page.locator('[data-system-state="permission_denied"]')).toBeVisible();

});

test("dashboard keeps a recoverable error state when aggregate service fails", async ({ page }) => {
  await mockCompanyApi(page, { overviewStatus: 500 });
  await page.goto("/company");
  await expect(page.locator('[data-system-state="error"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "ลองอีกครั้ง" })).toBeVisible();
});

test("context switch requests a signed branch token and replaces persisted branch scope", async ({ page }) => {
  await mockCompanyApi(page);
  const switchRequest = page.waitForRequest((request) => request.url().endsWith("/api/v1/auth/switch-branch"));
  await page.goto("/company");
  await page.getByTestId("company-context-switcher").click();
  await page.getByText("สาขาเชียงใหม่", { exact: true }).click();
  const request = await switchRequest;
  expect((request.postDataJSON() as { branch_id: string }).branch_id).toBe(secondBranchId);
  await expect.poll(async () => page.evaluate(() => JSON.parse(window.localStorage.getItem("erp-auth") ?? "{}").state?.branchId)).toBe(secondBranchId);
});

test("governance shows real evidence, planned gaps and Production HOLD on desktop and tablet", async ({ page }) => {
  await mockCompanyApi(page);
  for (const viewport of [{ width: 1440, height: 900 }, { width: 820, height: 1180 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/company/governance");
    await expect(page.getByTestId("company-governance-page")).toBeVisible();
    await expect(page.getByText("Production activation", { exact: true })).toBeVisible();
    await expect(page.getByText("hold", { exact: true }).nth(1)).toBeVisible();
    await expect(page.getByText("Incident Management", { exact: true })).toBeVisible();
    await expect(page.getByText("planned", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Hotel PMS", { exact: true })).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
  }
});
