import { expect, test, type Page, type Route } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const operator = {
  id: "22222222-2222-4222-8222-222222222222",
  username: "platform.owner",
  email: "owner@example.com",
  display_name: "Platform Owner",
  is_superuser: true,
  mfa_enabled: false,
  last_login_at: "2026-08-03T08:00:00Z",
};

const company = {
  id: companyId,
  name: "ร้านทดสอบ SaaS",
  name_en: "SaaS Test Restaurant",
  tax_id: null,
  email: "tenant@example.com",
  is_active: true,
  credential_version: 1,
  plan_code: "starter",
  created_at: "2026-08-03T08:00:00Z",
  suspended_at: null,
};

function response<T>(data: T): { data: T; meta: { version: string; identity_database: string }; error: null } {
  return {
    data,
    meta: { version: "test", identity_database: "legacy" },
    error: null,
  };
}

async function fulfill(route: Route, data: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(data),
  });
}

async function installAuthenticatedSession(page: Page): Promise<void> {
  await page.addInitScript((operatorValue) => {
    window.sessionStorage.setItem(
      "restaurant-platform-auth",
      JSON.stringify({
        state: {
          accessToken: "platform-test-token",
          csrfToken: "platform-csrf-token",
          sessionId: "44444444-4444-4444-8444-444444444444",
          operator: operatorValue,
        },
        version: 0,
      }),
    );
  }, operator);
}

const populatedDashboard = response({
  generated_at: "2026-08-03T08:30:00Z",
  totals: {
    companies: 1,
    active_companies: 1,
    suspended_companies: 0,
    brands: 1,
    branches: 1,
    enabled_user_accounts: 2,
    devices: 1,
    paired_devices: 1,
  },
  onboarding: { ready_companies: 1, pending_companies: 0, total_active_companies: 1 },
  product_status: { restaurant: "pilot", takeaway: "planned", retail_pos: "planned" },
  feature_usage: { restaurant: 1, takeaway: 0, retail_pos: 0 },
  plan_usage: { starter: 1 },
  recent_companies: [{ ...company, onboarding_complete: true, completed_steps: 7, total_steps: 7 }],
  recent_events: [{
    id: "33333333-3333-4333-8333-333333333333",
    company_id: companyId,
    operator_id: operator.id,
    action: "platform.company.create",
    resource: "Company",
    resource_id: companyId,
    old_value: null,
    new_value: { reason: "เปิด Pilot" },
    ip_address: "127.0.0.1",
    created_at: "2026-08-03T08:00:00Z",
  }],
});

test("Platform Owner login opens dashboard and can reach company and audit views", async ({ page }) => {
  await page.route("**/api/v1/platform/auth/login", async (route) => {
    await fulfill(route, response({
      access_token: "platform-test-token",
      token_type: "bearer",
      expires_in: 900,
      csrf_token: "platform-csrf-token",
      session_id: "44444444-4444-4444-8444-444444444444",
      operator,
    }));
  });
  await page.route("**/api/v1/platform/dashboard", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    await fulfill(route, populatedDashboard);
  });
  await page.route("**/api/v1/platform/companies", async (route) => {
    await fulfill(route, response([company]));
  });
  await page.route(`**/api/v1/platform/companies/${companyId}`, async (route) => {
    await fulfill(route, response({
      ...company,
      phone: null,
      currency: "THB",
      timezone: "Asia/Bangkok",
      controls: {
        plan_code: "starter",
        feature_flags: { restaurant: true, takeaway: false, retail_pos: false },
        plan_limits: { brands: 1, branches: 1, users: 10, devices: 3 },
      },
      onboarding: {
        complete: true,
        completed_steps: 6,
        total_steps: 6,
        steps: [
          { key: "product", label: "Restaurant pilot", complete: true, count: 1, target: 1 },
          { key: "company", label: "Company", complete: true, count: 1, target: 1 },
          { key: "brand", label: "Brand", complete: true, count: 1, target: 1 },
          { key: "branch", label: "Branch", complete: true, count: 1, target: 1 },
          { key: "menu", label: "Menu", complete: true, count: 1, target: 1 },
          { key: "staff", label: "Staff", complete: true, count: 1, target: 1 },
        ],
      },
      suspension_reason: null,
      reactivated_at: null,
      reactivation_reason: null,
      updated_at: "2026-08-03T08:00:00Z",
    }));
  });
  await page.route("**/api/v1/platform/audit", async (route) => {
    await fulfill(route, response(populatedDashboard.data.recent_events));
  });
  await page.route("**/api/v1/platform/auth/sessions", async (route) => {
    await fulfill(route, response([{
      id: "44444444-4444-4444-8444-444444444444",
      current: true,
      created_at: "2026-08-03T08:00:00Z",
      last_seen_at: "2026-08-03T08:30:00Z",
      expires_at: "2026-09-02T08:00:00Z",
      mfa_verified_at: null,
      revoked_at: null,
      ip_address: "127.0.0.1",
      user_agent: "Chrome",
    }]));
  });

  await page.goto("/platform/login");
  await page.locator("#platform-username").fill("platform.owner");
  await page.locator("#platform-password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "เข้าสู่ Platform Console" }).click();

  await expect(page).toHaveURL(/\/platform\/dashboard$/);
  await expect(page.getByLabel("กำลังโหลดภาพรวม Platform")).toBeVisible();
  await expect(page.getByRole("heading", { name: "ภาพรวมระบบ" })).toBeVisible();
  await expect(page.getByText("PILOT", { exact: true })).toBeVisible();
  await expect(page.getByText("PLANNED", { exact: true })).toHaveCount(2);
  await expect(page.getByText("บัญชีผู้ใช้ที่เปิดใช้งาน")).toBeVisible();

  await page.getByRole("link", { name: /จัดการบริษัทลูกค้า/ }).click();
  await expect(page.getByRole("heading", { name: "บริษัทลูกค้า" })).toBeVisible();
  await page.getByText(company.name, { exact: true }).click();
  await expect(page.getByRole("heading", { name: company.name })).toBeVisible();
  await expect(page.getByText("Restaurant pilot", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: /Audit Log/ }).click();
  await expect(page.getByRole("heading", { name: "Platform Audit Log" })).toBeVisible();
  await expect(page.getByText("platform.company.create", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /ความปลอดภัย/ }).click();
  await expect(page.getByRole("heading", { name: "ความปลอดภัย" })).toBeVisible();
  await expect(page.getByText("เครื่องนี้", { exact: true })).toBeVisible();
});

test("dashboard presents error then recovers to an empty state", async ({ page }) => {
  await installAuthenticatedSession(page);
  let requestCount = 0;
  await page.route("**/api/v1/platform/dashboard", async (route) => {
    requestCount += 1;
    if (requestCount <= 2) {
      await fulfill(route, { detail: "dashboard unavailable" }, 500);
      return;
    }
    await fulfill(route, response({
      generated_at: "2026-08-03T08:30:00Z",
      totals: {
        companies: 0,
        active_companies: 0,
        suspended_companies: 0,
        brands: 0,
        branches: 0,
        enabled_user_accounts: 0,
        devices: 0,
        paired_devices: 0,
      },
      onboarding: { ready_companies: 0, pending_companies: 0, total_active_companies: 0 },
      product_status: { restaurant: "pilot", takeaway: "planned", retail_pos: "planned" },
      feature_usage: { restaurant: 0, takeaway: 0, retail_pos: 0 },
      plan_usage: {},
      recent_companies: [],
      recent_events: [],
    }));
  });

  await page.goto("/platform/dashboard");
  await expect(page.getByRole("heading", { name: "โหลดภาพรวม Platform ไม่สำเร็จ" })).toBeVisible();
  await expect(page.getByText("dashboard unavailable")).toBeVisible();
  await page.getByRole("button", { name: /ลองใหม่/ }).click();
  await expect(page.getByText("ยังไม่มีบริษัทลูกค้า")).toBeVisible();
  await expect(page.getByText("ยังไม่มีกิจกรรม")).toBeVisible();
  await expect(page.getByText("ยังไม่มีข้อมูล Plan")).toBeVisible();
});

test("missing or rejected Platform credentials return to the restricted login", async ({ page }) => {
  await page.goto("/platform/dashboard");
  await expect(page).toHaveURL(/\/platform\/login\?next=/);

  await installAuthenticatedSession(page);
  await page.route("**/api/v1/platform/dashboard", async (route) => {
    await fulfill(route, { detail: "Invalid token type" }, 401);
  });
  await page.route("**/api/v1/platform/auth/refresh", async (route) => {
    await fulfill(route, { detail: "Platform session is invalid or revoked" }, 401);
  });
  await page.goto("/platform/dashboard");
  await expect(page).toHaveURL(/\/platform\/login\?next=/);
  await expect(page.getByText("Restricted workspace", { exact: true })).toBeVisible();
});

test("Platform Owner can enroll MFA and receives one-time recovery codes", async ({ page }) => {
  await installAuthenticatedSession(page);
  await page.route("**/api/v1/platform/auth/sessions", async (route) => {
    await fulfill(route, response([]));
  });
  await page.route("**/api/v1/platform/auth/mfa/setup", async (route) => {
    await fulfill(route, response({
      secret: "JBSWY3DPEHPK3PXP",
      provisioning_uri: "otpauth://totp/Restaurant%20Platform%3Aplatform.owner?secret=JBSWY3DPEHPK3PXP",
    }));
  });
  await page.route("**/api/v1/platform/auth/mfa/confirm", async (route) => {
    await fulfill(route, response({
      recovery_codes: ["ABCD-EFGH-JKLM", "NPQR-STUV-WXYZ"],
      operator: { ...operator, mfa_enabled: true },
    }));
  });

  await page.goto("/platform/security");
  await page.getByRole("button", { name: "เริ่มตั้งค่า MFA" }).click();
  await expect(page.getByAltText("Platform MFA QR code")).toBeVisible();
  await expect(page.getByText(/Secret: JBSWY3DPEHPK3PXP/)).toBeVisible();
  await page.locator("#mfa-confirm-code").fill("123456");
  await page.getByRole("button", { name: "ยืนยันและเปิด MFA" }).click();
  await expect(page.getByText("ABCD-EFGH-JKLM", { exact: true })).toBeVisible();
  await expect(page.getByText(/ระบบจะแสดงครั้งเดียว/)).toBeVisible();
});
