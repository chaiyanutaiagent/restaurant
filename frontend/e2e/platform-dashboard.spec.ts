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
  business_slug: "saas-test-restaurant",
  name_en: "SaaS Test Restaurant",
  tax_id: null,
  email: "tenant@example.com",
  is_active: true,
  credential_version: 1,
  plan_code: "starter",
  created_at: "2026-08-03T08:00:00Z",
  suspended_at: null,
};

const tenantAccessToken = `header.${Buffer.from(JSON.stringify({ permissions: [], branch_id: null })).toString("base64url")}.signature`;

const starterPlan = {
  id: "55555555-5555-4555-8555-555555555555",
  code: "starter",
  name: "Starter",
  description: "Price decision pending",
  currency: "THB",
  billing_interval: "month",
  unit_amount_satang: null,
  feature_flags: { restaurant: true, retail_pos: false, takeaway: false },
  plan_limits: { brands: 1, branches: 1, users: 10, devices: 3 },
  is_public: false,
  is_active: true,
  created_at: "2026-08-03T08:00:00Z",
  updated_at: "2026-08-03T08:00:00Z",
};

const billingSummary = {
  company_id: companyId,
  provider: "unconfigured",
  live_charging_enabled: false,
  collection_available: false,
  plan: starterPlan,
  subscription: {
    id: "66666666-6666-4666-8666-666666666666",
    company_id: companyId,
    plan_id: starterPlan.id,
    status: "trialing",
    current_period_start: "2026-08-03T08:00:00Z",
    current_period_end: "2026-08-17T08:00:00Z",
    trial_started_at: "2026-08-03T08:00:00Z",
    trial_ends_at: "2026-08-17T08:00:00Z",
    cancel_at_period_end: false,
    cancelled_at: null,
    created_at: "2026-08-03T08:00:00Z",
    updated_at: "2026-08-03T08:00:00Z",
  },
  invoices: [],
};

const privacyRequest = {
  id: "88888888-8888-4888-8888-888888888888",
  company_id: companyId,
  requester_user_id: "77777777-7777-4777-8777-777777777777",
  request_type: "access",
  subject_email: "tenant@example.com",
  description: "ขอตรวจสอบข้อมูลระดับบัญชี",
  status: "submitted",
  identity_verification: "authenticated_owner",
  target_at: "2026-09-02T08:00:00Z",
  response_summary: null,
  decision_reason: null,
  reviewed_by: null,
  completed_at: null,
  created_at: "2026-08-03T08:00:00Z",
  updated_at: "2026-08-03T08:00:00Z",
};

const supportGrant = {
  id: "99999999-9999-4999-8999-999999999999",
  ticket_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  company_id: companyId,
  requested_by_operator_id: operator.id,
  requested_scopes: ["account_state", "saas_controls", "billing_state"],
  purpose: "ตรวจสอบ aggregate lifecycle เท่านั้น",
  duration_minutes: 30,
  status: "pending",
  decided_by_user_id: null,
  decision_reason: null,
  decided_at: null,
  expires_at: null,
  last_accessed_at: null,
  revoked_at: null,
  revoked_by_type: null,
  revoke_reason: null,
  created_at: "2026-08-03T08:00:00Z",
  updated_at: "2026-08-03T08:00:00Z",
};

const supportTicket = {
  id: supportGrant.ticket_id,
  ticket_number: "SUP-20260803-TEST0001",
  company_id: companyId,
  requester_user_id: privacyRequest.requester_user_id,
  category: "technical",
  priority: "high",
  status: "open",
  subject: "Account status differs from billing",
  assigned_operator_id: null,
  closed_at: null,
  created_at: "2026-08-03T08:00:00Z",
  updated_at: "2026-08-03T08:00:00Z",
  messages: [],
  access_grants: [],
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
  attention_summary: { companies: 1, unpaired_devices: 1 },
  feature_usage: { restaurant: 1, takeaway: 0, retail_pos: 0 },
  plan_usage: { starter: 1 },
  recent_companies: [{
    ...company,
    onboarding_complete: true,
    completed_steps: 7,
    total_steps: 7,
    last_activity_at: "2026-08-03T08:25:00Z",
    attention_codes: ["unpaired_devices"],
  }],
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
  await page.route("**/api/v1/platform/usage/snapshots", async (route) => {
    await fulfill(route, response([]));
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
      membership: {
        company_id: companyId,
        owner_email: "public-owner@example.com",
        status: "trial_active",
        onboarding_state: "setup_required",
        email_verified_at: "2026-08-03T08:00:00Z",
        trial_started_at: "2026-08-03T08:00:00Z",
        trial_ends_at: "2026-08-17T08:00:00Z",
        trial_days_remaining: 14,
      },
      suspension_reason: null,
      reactivated_at: null,
      reactivation_reason: null,
      updated_at: "2026-08-03T08:00:00Z",
    }));
  });
  await page.route(`**/api/v1/platform/companies/${companyId}/usage`, async (route) => {
    await fulfill(route, response({
      company_id: companyId,
      generated_at: "2026-08-03T08:30:00Z",
      plan_code: "starter",
      feature_flags: { restaurant: true, takeaway: false, retail_pos: false },
      plan_limits: { brands: 1, branches: 1, users: 10, devices: 3 },
      usage: {
        brands: 1,
        branches: 1,
        enabled_user_accounts: 2,
        registered_devices: 1,
        paired_devices: 1,
        active_menu_items: 8,
      },
      limit_state: {
        brands: { resource_key: "brands", current: 1, limit: 1, unlimited: false, exceeded: false, remaining: 0, utilization_percent: 100 },
        branches: { resource_key: "branches", current: 1, limit: 1, unlimited: false, exceeded: false, remaining: 0, utilization_percent: 100 },
        users: { resource_key: "enabled_user_accounts", current: 2, limit: 10, unlimited: false, exceeded: false, remaining: 8, utilization_percent: 20 },
        devices: { resource_key: "registered_devices", current: 1, limit: 3, unlimited: false, exceeded: false, remaining: 2, utilization_percent: 33 },
      },
      attention_codes: [],
      last_activity_at: "2026-08-03T08:25:00Z",
      onboarding_completed_steps: 7,
      onboarding_total_steps: 7,
    }));
  });
  await page.route(`**/api/v1/platform/companies/${companyId}/usage/history`, async (route) => {
    await fulfill(route, response([]));
  });
  await page.route(`**/api/v1/platform/companies/${companyId}/billing`, async (route) => {
    await fulfill(route, response(billingSummary));
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
  await expect(page.getByText("Foodchainservice Platform", { exact: true })).toBeVisible();
  await expect(page.getByLabel("กำลังโหลดภาพรวม Platform")).toBeVisible();
  await expect(page.getByRole("heading", { name: "ภาพรวมระบบ" })).toBeVisible();
  await expect(page.getByText("PILOT", { exact: true })).toBeVisible();
  await expect(page.getByText("PLANNED", { exact: true })).toHaveCount(2);
  await expect(page.getByText("บัญชีผู้ใช้ที่เปิดใช้งาน")).toBeVisible();
  await expect(page.getByText(/มีอุปกรณ์รอจับคู่/).first()).toBeVisible();
  await page.getByRole("button", { name: /บันทึก Usage วันนี้/ }).click();
  await expect(page.getByText(/บันทึก aggregate usage snapshot วันนี้แล้ว/)).toBeVisible();

  await page.getByRole("link", { name: /จัดการบริษัทลูกค้า/ }).click();
  await expect(page.getByRole("heading", { name: "บริษัทลูกค้า" })).toBeVisible();
  await page.getByText(company.name, { exact: true }).click();
  await expect(page.getByRole("heading", { name: company.name })).toBeVisible();
  await expect(page.getByText("Restaurant pilot", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "การใช้ทรัพยากรตาม Plan" })).toBeVisible();
  await expect(page.getByText("trial_active", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Subscription และ Invoice" })).toBeVisible();

  await page.getByRole("link", { name: /Audit Log/ }).click();
  await expect(page.getByRole("heading", { name: "Platform Audit Log" })).toBeVisible();
  await expect(page.getByText("platform.company.create", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /ความปลอดภัย/ }).click();
  await expect(page.getByRole("heading", { name: "ความปลอดภัย" })).toBeVisible();
  await expect(page.getByText("เครื่องนี้", { exact: true })).toBeVisible();
});

test("Platform billing keeps live collection closed and records plan pricing in satang", async ({ page }) => {
  await installAuthenticatedSession(page);
  let savedPlan = starterPlan;
  let capturedPayload: Record<string, unknown> | null = null;
  await page.route("**/api/v1/platform/billing/overview", async (route) => {
    await fulfill(route, response({
      provider: "unconfigured",
      live_charging_enabled: false,
      collection_available: false,
      plans: [savedPlan],
      subscription_counts: { trialing: 1 },
      invoice_counts: {},
    }));
  });
  await page.route("**/api/v1/platform/billing/plans", async (route) => {
    capturedPayload = route.request().postDataJSON() as Record<string, unknown>;
    savedPlan = { ...starterPlan, unit_amount_satang: capturedPayload.unit_amount_satang as number };
    await fulfill(route, response(savedPlan));
  });

  await page.goto("/platform/billing");
  await expect(page.getByRole("heading", { name: "Plan และ Billing" })).toBeVisible();
  await expect(page.getByText("ยังไม่เปิดรับเงินจริง", { exact: true })).toBeVisible();
  await page.getByLabel("ราคาต่อรอบ (บาท)").fill("990.00");
  await page.getByLabel("เหตุผล").fill("กำหนดราคา beta catalog");
  await page.getByRole("button", { name: /บันทึก Plan/ }).click();
  await expect.poll(() => capturedPayload?.unit_amount_satang).toBe(99000);
  await expect(page.getByText(/฿990.00/)).toBeVisible();
});

test("Tenant owner sees a read-only billing status without a payment action", async ({ page }) => {
  await page.addInitScript(({ company, tenant }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({
      state: {
        accessToken: "tenant-access-token",
        refreshToken: "tenant-refresh-token",
        user: tenant,
        companyId: company,
        branchId: null,
        stationKey: null,
        permissions: [],
      },
      version: 0,
    }));
  }, {
    company: companyId,
    tenant: { id: "77777777-7777-4777-8777-777777777777", username: "tenant.owner", display_name: "Tenant Owner" },
  });
  await page.route("**/api/v1/membership/billing", async (route) => {
    await fulfill(route, { data: billingSummary, meta: { version: "test" }, error: null });
  });
  await page.route("**/api/v1/system/me/branches", async (route) => {
    await fulfill(route, { data: [], meta: { version: "test" }, error: null });
  });
  await page.route("**/api/v1/restaurant/me/brand-navigation", async (route) => {
    await fulfill(route, { data: [], meta: { version: "test" }, error: null });
  });

  await page.goto("/billing");
  await expect(page.getByRole("heading", { name: "แพ็กเกจและการเรียกเก็บเงิน" })).toBeVisible();
  await expect(page.getByText("ระบบรับชำระค่าสมาชิกยังไม่เปิดใช้งาน", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /ชำระ|บัตร|checkout/i })).toHaveCount(0);
});

test("Platform requests named support access and cannot silently impersonate a Tenant", async ({ page }) => {
  await installAuthenticatedSession(page);
  let capturedAccess: Record<string, unknown> | null = null;
  let tickets = [supportTicket];
  await page.route("**/api/v1/platform/privacy/requests", async (route) => {
    await fulfill(route, response([privacyRequest]));
  });
  await page.route("**/api/v1/platform/support/tickets", async (route) => {
    await fulfill(route, response(tickets));
  });
  await page.route(`**/api/v1/platform/support/tickets/${supportTicket.id}/access`, async (route) => {
    capturedAccess = route.request().postDataJSON() as Record<string, unknown>;
    tickets = [{ ...supportTicket, access_grants: [supportGrant] }];
    await fulfill(route, response(supportGrant), 201);
  });

  await page.goto("/platform/support");
  await expect(page.getByRole("heading", { name: "Privacy & Support" })).toBeVisible();
  await expect(page.getByText(/ไม่มี impersonation token/)).toBeVisible();
  await page.getByLabel("เหตุผล / วัตถุประสงค์สำหรับ Audit Log").fill("ขอ aggregate context เพื่อแก้ ticket");
  await page.getByRole("button", { name: "ขอ Access 30 นาที" }).click();
  await expect.poll(() => capturedAccess?.duration_minutes).toBe(30);
  await expect.poll(() => capturedAccess?.requested_scopes).toEqual(["account_state", "saas_controls", "billing_state"]);
  await expect(page.getByText("รอ Tenant อนุมัติ", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Impersonate|สวมรอย|เข้าสู่ระบบแทน/i })).toHaveCount(0);
});

test("Tenant owner submits a privacy request and decides a time-limited support grant", async ({ page }) => {
  await page.addInitScript(({ company, tenant }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({ state: { accessToken: "tenant-access-token", refreshToken: "tenant-refresh-token", user: tenant, companyId: company, branchId: null, stationKey: null, permissions: [] }, version: 0 }));
  }, { company: companyId, tenant: { id: privacyRequest.requester_user_id, username: "tenant.owner", display_name: "Tenant Owner" } });
  let privacyRows: typeof privacyRequest[] = [];
  let capturedDecision: Record<string, unknown> | null = null;
  let ticketRows = [{ ...supportTicket, access_grants: [supportGrant] }];
  await page.route("**/api/v1/privacy-support/privacy-requests", async (route) => {
    if (route.request().method() === "POST") {
      privacyRows = [privacyRequest];
      await fulfill(route, { data: privacyRequest, meta: { version: "test" }, error: null }, 201);
      return;
    }
    await fulfill(route, { data: privacyRows, meta: { version: "test" }, error: null });
  });
  await page.route("**/api/v1/privacy-support/tickets", async (route) => {
    await fulfill(route, { data: ticketRows, meta: { version: "test" }, error: null });
  });
  await page.route(`**/api/v1/privacy-support/access/${supportGrant.id}/decision`, async (route) => {
    capturedDecision = route.request().postDataJSON() as Record<string, unknown>;
    ticketRows = [{ ...supportTicket, access_grants: [{ ...supportGrant, status: "approved", expires_at: "2026-08-03T09:00:00Z" }] }];
    await fulfill(route, { data: ticketRows[0].access_grants[0], meta: { version: "test" }, error: null });
  });
  await page.route("**/api/v1/system/me/branches", async (route) => { await fulfill(route, { data: [], meta: { version: "test" }, error: null }); });
  await page.route("**/api/v1/restaurant/me/brand-navigation", async (route) => { await fulfill(route, { data: [], meta: { version: "test" }, error: null }); });

  await page.goto("/privacy-support");
  await expect(page.getByRole("heading", { name: "ความเป็นส่วนตัวและการช่วยเหลือ" })).toBeVisible();
  await page.getByLabel("รายละเอียด").first().fill("ขอตรวจสอบข้อมูลบัญชี");
  await page.getByRole("button", { name: "ส่งคำขอ" }).click();
  await expect(page.locator("article").getByText("access", { exact: true })).toBeVisible();
  await page.getByLabel("เหตุผลการตัดสินใจ support access").fill("อนุมัติเฉพาะขอบเขตและเวลาที่ระบุ");
  await page.getByRole("button", { name: "อนุมัติ" }).click();
  await expect.poll(() => capturedDecision?.decision).toBe("approved");
  await expect(page.getByText("คำขอสิทธิ์ช่วยเหลือรออนุมัติ", { exact: true })).toHaveCount(0);
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
      attention_summary: { companies: 0 },
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
  await expect(page.getByText("Foodchainservice Platform", { exact: true })).toBeVisible();
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

test("Foodchainservice public workspace shows active modules without exposing dark launch routes", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle("Foodchainservice");
  await expect(page.getByText("Foodchainservice", { exact: true })).toBeVisible();
  await expect(page.getByTestId("workspace-module-erp")).toHaveAttribute("href", "/login?next=%2Fadmin");
  await expect(page.getByTestId("workspace-module-central_kitchen")).toHaveAttribute(
    "href",
    "/login?next=%2Frestaurant%2Fbrands",
  );
  await expect(page.getByTestId("workspace-module-restaurant_pos")).toBeVisible();
  await expect(page.getByTestId("workspace-module-retail_pos")).toBeVisible();
  await expect(page.getByTestId("workspace-module-hotel_pms")).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByTestId("workspace-module-takeaway_pos")).toHaveCount(0);
});

test("Foodchainservice workspace reveals dark launch Takeaway only to an authorized user", async ({ page }) => {
  await page.addInitScript(({ company, token }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({
      state: {
        accessToken: token,
        refreshToken: "tenant-refresh-token",
        user: {
          id: "77777777-7777-4777-8777-777777777777",
          company_id: company,
          username: "takeaway.operator",
          display_name: "Takeaway Operator",
          is_active: true,
        },
        companyId: company,
        businessSlug: "takeaway-test",
        branchId: null,
        stationKey: null,
        permissions: ["takeaway.catalog.view"],
      },
      version: 0,
    }));
  }, { company: companyId, token: tenantAccessToken });
  await page.route("**/api/v1/restaurant/me/brand-navigation", async (route) => {
    await fulfill(route, response([]));
  });

  await page.goto("/");

  await expect(page.getByTestId("workspace-module-takeaway_pos")).toHaveAttribute("href", "/takeaway");
  await expect(page.getByTestId("workspace-module-restaurant_pos")).toHaveCount(0);
  await expect(page.getByTestId("workspace-module-retail_pos")).toHaveCount(0);
  await expect(page.getByTestId("workspace-module-central_kitchen")).toHaveCount(0);
  await expect(page.getByTestId("workspace-module-erp")).toBeVisible();
  await expect(page.getByTestId("workspace-module-hotel_pms")).toHaveAttribute("aria-disabled", "true");
});

test("Restaurant, Retail, and Takeaway entry routes keep their existing authentication guards", async ({ page }) => {
  for (const path of ["/restaurant", "/pos", "/takeaway"]) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`/login\\?next=${encodeURIComponent(path)}$`));
    await expect(page.getByText("Foodchainservice Company Admin", { exact: true })).toBeVisible();
  }
});

test("public SaaS owner can complete signup, verification, and password recovery pages", async ({ page }) => {
  await page.route("**/api/v1/membership/signup", async (route) => {
    await fulfill(route, response({
      company_id: companyId,
      business_slug: "public-saas-restaurant",
      status: "pending_verification",
      verification_required: true,
      message: "Account created; check your email to verify the account",
    }), 201);
  });
  await page.route("**/api/v1/membership/verification/confirm", async (route) => {
    await fulfill(route, response({
      message: "Email verified; the SaaS trial is active",
      membership: {
        company_id: companyId,
        owner_email: "public-owner@example.com",
        status: "trial_active",
        onboarding_state: "setup_required",
        email_verified_at: "2026-08-03T08:00:00Z",
        trial_started_at: "2026-08-03T08:00:00Z",
        trial_ends_at: "2026-08-17T08:00:00Z",
        trial_days_remaining: 14,
      },
    }));
  });
  await page.route("**/api/v1/membership/password-reset/request", async (route) => {
    await fulfill(route, response({ message: "If the account is eligible, an email has been accepted for delivery", membership: null }), 202);
  });
  await page.route("**/api/v1/membership/password-reset/confirm", async (route) => {
    await fulfill(route, response({ message: "Password reset; previous refresh sessions were revoked", membership: null }));
  });

  await page.goto("/signup");
  await expect(page).toHaveTitle("Foodchainservice");
  await expect(page.getByText("Foodchainservice Customer Register", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "เลือกประเภทระบบสำหรับธุรกิจของคุณ" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Restaurant POS" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Retail POS" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Takeaway POS" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hotel PMS" })).toBeVisible();
  await expect(page.getByTestId("signup-product-retail_pos")).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByTestId("signup-product-takeaway_pos")).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByTestId("signup-product-hotel_pms")).toHaveAttribute("aria-disabled", "true");
  await page.getByTestId("signup-product-restaurant_pos").click();
  await expect(page).toHaveURL(/\/signup\/restaurant$/);
  await page.locator("#company_name").fill("ร้านสมาชิก SaaS");
  await page.locator("#business_slug").fill("public-saas-restaurant");
  await page.locator("#owner_display_name").fill("เจ้าของร้าน");
  await page.locator("#owner_email").fill("public-owner@example.com");
  await page.locator("#username").fill("public.owner");
  await page.locator("#password").fill("Public-Owner-Password!");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "เริ่มทดลองใช้" }).click();
  await expect(page.getByText("สร้างบัญชีแล้ว กรุณาตรวจอีเมลเพื่อยืนยัน")).toBeVisible();
  await expect(page.getByText("/public-saas-restaurant", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "ไปหน้าเข้าสู่ระบบของธุรกิจ" })).toHaveAttribute("href", "/public-saas-restaurant/login");

  await page.goto("/verify-email#token=browser-verification-token-1234567890");
  await page.getByRole("button", { name: "ยืนยันอีเมล" }).click();
  await expect(page.getByText("ยืนยันสำเร็จและเริ่มช่วงทดลองใช้แล้ว")).toBeVisible();
  await expect(page.getByRole("link", { name: "เข้าสู่ระบบ" })).toHaveAttribute("href", "/public-saas-restaurant/login");

  await page.goto("/forgot-password");
  await page.locator("#email").fill("public-owner@example.com");
  await page.getByRole("button", { name: "ขอลิงก์ตั้งรหัสผ่าน" }).click();
  await expect(page.getByText(/หากอีเมลนี้มีสิทธิ์/)).toBeVisible();

  await page.goto("/reset-password#token=browser-reset-token-1234567890");
  await page.locator("#new-password").fill("Public-Owner-New-Password!");
  await page.getByRole("button", { name: "บันทึกรหัสผ่านใหม่" }).click();
  await expect(page.getByText(/session เดิมถูกเพิกถอน/)).toBeVisible();
});

test("Platform Owner can review protected operations and capture a runtime snapshot", async ({ page }) => {
  await installAuthenticatedSession(page);
  let runtimeCaptured = false;
  const operationsSnapshot = {
    id: "55555555-5555-4555-8555-555555555555",
    captured_at: "2026-08-03T09:00:00Z",
    overall_status: "ok",
    source: "resilience_import",
    component_checks: { public_api: "ok", reference_projector: "ok" },
    projector_failed_events: 0,
    projector_loop_errors: 0,
    disk_usage_percent: 35,
    backup_status: "current",
    backup_age_hours: 2,
    restore_status: "passed",
    restore_drill_at: "2026-08-03T08:00:00Z",
    alert_delivery_status: "not_configured",
    alert_codes: [],
    evidence_sha256: "a".repeat(64),
    captured_by: operator.id,
    created_at: "2026-08-03T09:00:00Z",
  };
  await page.route("**/api/v1/platform/operations/summary", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 200));
    await fulfill(route, response({
      generated_at: "2026-08-03T09:00:00Z",
      runtime: {
        status: "ok",
        component_checks: {
          legacy_database: "ok",
          platform_database: "ok",
          restaurant_database: "ok",
          redis: "ok",
          uploads: "ok",
          reference_projector: "disabled",
        },
        projector_failed_events: 0,
        projector_loop_errors: 0,
        disk_usage_percent: 35,
      },
      latest_snapshot: operationsSnapshot,
      latest_backup: operationsSnapshot,
      latest_restore: operationsSnapshot,
      latest_alert: operationsSnapshot,
    }));
  });
  await page.route("**/api/v1/platform/operations/history", async (route) => {
    await fulfill(route, response(runtimeCaptured ? [{ ...operationsSnapshot, source: "operator_runtime" }] : [operationsSnapshot]));
  });
  await page.route("**/api/v1/platform/operations/capture", async (route) => {
    runtimeCaptured = true;
    await fulfill(route, response({ ...operationsSnapshot, source: "operator_runtime" }));
  });

  await page.goto("/platform/operations");
  await expect(page.getByLabel("กำลังโหลดสถานะ Operations")).toBeVisible();
  await expect(page.getByRole("heading", { name: "สถานะระบบและ Recovery" })).toBeVisible();
  await expect(page.getByText("Legacy database", { exact: true })).toBeVisible();
  await expect(page.getByText("current", { exact: true })).toBeVisible();
  await expect(page.getByText("passed", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "บันทึก Runtime snapshot" }).click();
  await expect(page.getByText("operator_runtime", { exact: true })).toBeVisible();
});

test("business slug opens only its canonical public storefront", async ({ page }) => {
  await page.route("**/api/public/storefront/businesses/alpha-cafe", async (route) => {
    await fulfill(route, response({
      company: {
        id: companyId,
        name: "Alpha Cafe",
        business_slug: "alpha-cafe",
        name_en: null,
        tax_id: null,
        vat_registered: false,
        address: null,
        phone: null,
        email: null,
        logo_url: null,
        website: null,
        currency: "THB",
        timezone: "Asia/Bangkok",
      },
      featured_products: [],
      branches: [],
    }));
  });
  await page.route("**/api/public/storefront/businesses/alpha-cafe/products**", async (route) => {
    await fulfill(route, {
      data: [{
        id: "aaaaaaaa-1111-4111-8111-111111111111",
        sku: "ALPHA-COFFEE",
        barcode: null,
        name: "Alpha Signature Coffee",
        name_en: null,
        description: "Only Alpha catalog",
        selling_price: 120,
        vat_type: "included",
        vat_rate: 7,
        category_id: null,
        category_name: null,
        unit_code: null,
        image_url: null,
        is_active: true,
        total_qty_available: 5,
        in_stock: true,
      }],
      meta: { version: "test", total: 1, page: 1, limit: 24 },
      error: null,
    });
  });

  await page.goto("/alpha-cafe");
  await expect(page.getByRole("heading", { name: "Alpha Cafe" })).toBeVisible();
  await expect(page.getByText("Alpha Signature Coffee", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "เข้าสู่ระบบแอดมิน" })).toHaveAttribute("href", "/alpha-cafe/admin");
  await expect(page.getByText("Beta Bistro", { exact: true })).toHaveCount(0);
});

test("business admin resolves Company ID, hides UUID entry, and keeps the canonical URL", async ({ page }) => {
  let loginCompanyHeader: string | undefined;
  await page.route("**/api/v1/membership/businesses/alpha-cafe", async (route) => {
    await fulfill(route, response({
      company_id: companyId,
      business_slug: "alpha-cafe",
      name: "Alpha Cafe",
      logo_url: null,
    }));
  });
  await page.route("**/api/v1/auth/login", async (route) => {
    loginCompanyHeader = route.request().headers()["x-company-id"];
    await fulfill(route, response({
      access_token: tenantAccessToken,
      refresh_token: "tenant-refresh-token",
      token_type: "bearer",
      expires_in: 900,
      business_slug: "alpha-cafe",
      user: {
        id: "77777777-7777-4777-8777-777777777777",
        company_id: companyId,
        username: "alpha.owner",
        email: "alpha@example.com",
        phone: null,
        first_name: null,
        last_name: null,
        display_name: "Alpha Owner",
        is_active: true,
        is_superuser: false,
        last_login_at: null,
      },
    }));
  });
  await page.route("**/api/v1/reports/dashboard**", async (route) => {
    await fulfill(route, response({ today_orders: 0, today_sales: 0, today_vat: 0, today_avg_order: 0, compared_yesterday_pct: null, low_stock_count: 0, total_products: 0, open_shifts_count: 0 }));
  });
  await page.route("**/api/v1/reports/sales/hourly**", async (route) => { await fulfill(route, response([])); });
  await page.route("**/api/v1/stock/balances**", async (route) => { await fulfill(route, response([])); });
  await page.route("**/api/v1/system/me/branches", async (route) => { await fulfill(route, response([])); });
  await page.route("**/api/v1/restaurant/me/brand-navigation", async (route) => { await fulfill(route, response([])); });

  await page.goto("/alpha-cafe/admin");
  await expect(page).toHaveURL(/\/alpha-cafe\/login\?next=/);
  await expect(page.getByText("Foodchainservice · พื้นที่ธุรกิจ /alpha-cafe", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Company ID")).toBeHidden();
  await page.getByLabel("Username").fill("alpha.owner");
  await page.getByLabel("Password").fill("Routing-Owner-Password!");
  await page.getByRole("button", { name: "เข้าสู่ระบบ" }).click();

  await expect(page).toHaveURL(/\/alpha-cafe\/admin$/);
  await expect.poll(() => loginCompanyHeader).toBe(companyId);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Company Admin" }).first()).toHaveAttribute("href", "/alpha-cafe/admin");
});

test("business admin rejects a session belonging to another Tenant", async ({ page }) => {
  await page.addInitScript(({ token, tenantCompanyId }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({
      state: {
        accessToken: token,
        refreshToken: "beta-refresh-token",
        user: { id: "88888888-8888-4888-8888-888888888888", company_id: tenantCompanyId, username: "beta.owner", display_name: "Beta Owner" },
        companyId: tenantCompanyId,
        businessSlug: "beta-bistro",
        branchId: null,
        stationKey: null,
        permissions: [],
      },
      version: 0,
    }));
  }, { token: tenantAccessToken, tenantCompanyId: "99999999-9999-4999-8999-999999999999" });
  await page.route("**/api/v1/membership/businesses/alpha-cafe", async (route) => {
    await fulfill(route, response({ company_id: companyId, business_slug: "alpha-cafe", name: "Alpha Cafe", logo_url: null }));
  });

  await page.goto("/alpha-cafe/admin");
  await expect(page).toHaveURL(/\/403$/);
});
