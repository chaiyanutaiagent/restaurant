import { expect, test, type Page } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const foreignId = "22222222-2222-4222-8222-222222222222";
const business = { company_id: companyId, business_slug: "test2", name: "Test Two", logo_url: null };
function tokens(company = companyId, slug = "test2", tokenCompany = company) {
  return {
    access_token: `header.${Buffer.from(JSON.stringify({ company_id: tokenCompany, permissions: ["*"], scope_types: ["company"] })).toString("base64url")}.signature`,
    refresh_token: "test-refresh", business_slug: slug, token_type: "bearer", expires_in: 900,
    user: { id: "33333333-3333-4333-8333-333333333333", company_id: company, username: "owner.test2", display_name: "Test Owner", is_active: true, is_superuser: false },
  };
}
async function mock(page: Page, existing = false) {
  if (existing) await page.addInitScript(({ foreignId, session }) => {
    localStorage.setItem("erp-auth", JSON.stringify({ state: {
      accessToken: session.access_token, refreshToken: session.refresh_token, user: session.user,
      companyId: foreignId, businessSlug: "foreign-company", branchId: "44444444-4444-4444-8444-444444444444", permissions: ["*"],
    }, version: 0 }));
    localStorage.setItem("last_company_id", foreignId);
  }, { foreignId, session: tokens(foreignId, "foreign-company") });
  let autoRequests = 0;
  await page.route("**/api/v1/**", (route) => route.fulfill({ status: 403, json: { detail: "Not part of login test" } }));
  await page.route("**/api/v1/membership/businesses/test2", (route) => route.fulfill({ json: { data: business } }));
  await page.route("**/api/v1/auth/uat/auto-login", (route) => {
    autoRequests++;
    return route.fulfill({ json: { data: tokens(foreignId, "foreign-company") } });
  });
  return () => autoRequests;
}
async function submit(page: Page) {
  await page.getByLabel("Username", { exact: true }).fill("owner.test2");
  await page.getByLabel("Password", { exact: true }).fill("test-owner-password");
  await page.getByRole("button", { name: "เข้าสู่ระบบ", exact: true }).click();
}

test("canonical login preserves foreign session until real owner login succeeds and never auto-logins", async ({ page }) => {
  const autoRequests = await mock(page, true);
  let attempts = 0;
  await page.route("**/api/v1/auth/login", (route) => {
    attempts++;
    const request = route.request();
    expect(request.headers()["x-company-id"]).toBe(companyId);
    expect(request.headers().authorization).toBeUndefined();
    expect(request.headers()["x-branch-id"]).toBeUndefined();
    expect(request.postDataJSON().company_id).toBe(companyId);
    return attempts === 1
      ? route.fulfill({ status: 401, json: { detail: "Invalid credentials" } })
      : route.fulfill({ json: { data: tokens() } });
  });
  await page.goto("/test2/login?next=%2Fforeign-company%2Fadmin");
  await expect(page.getByText("เข้าสู่ระบบ · Test Two", { exact: true })).toBeVisible();
  expect(autoRequests()).toBe(0);
  await submit(page);
  await expect(page.getByText("ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/\/test2\/login\?/);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("erp-auth")!).state.companyId)).toBe(foreignId);
  await submit(page);
  await expect(page).toHaveURL(/\/test2\/admin$/);
  const state = await page.evaluate(() => JSON.parse(localStorage.getItem("erp-auth")!).state);
  expect(state.companyId).toBe(companyId);
  expect(state.businessSlug).toBe("test2");
  expect(state.branchId).toBeNull();
  expect(autoRequests()).toBe(0);
});

for (const mismatch of ["company", "slug", "token"] as const) {
  test(`canonical login rejects ${mismatch} mismatch without replacing old identity`, async ({ page }) => {
    const autoRequests = await mock(page, true);
    await page.route("**/api/v1/auth/login", (route) => route.fulfill({ json: { data:
      tokens(mismatch === "company" ? foreignId : companyId, mismatch === "slug" ? "foreign-company" : "test2", mismatch === "token" ? foreignId : companyId),
    } }));
    await page.goto("/test2/login");
    await submit(page);
    await expect(page.getByText(/ไม่ตรงกับบริษัทในลิงก์/)).toBeVisible();
    await expect(page).toHaveURL(/\/test2\/login$/);
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem("erp-auth")!).state.companyId)).toBe(foreignId);
    expect(autoRequests()).toBe(0);
  });
}

test("canonical admin with a foreign identity returns to company login instead of 403", async ({ page }) => {
  const autoRequests = await mock(page, true);
  await page.goto("/test2/admin");
  await expect(page).toHaveURL(/\/test2\/login\?next=/);
  await expect(page.getByRole("button", { name: "เข้าสู่ระบบ", exact: true })).toBeVisible();
  expect(autoRequests()).toBe(0);
});

test("canonical login rejects public business metadata for a different slug", async ({ page }) => {
  await mock(page);
  await page.route("**/api/v1/membership/businesses/test2", (route) => route.fulfill({ json: { data: { ...business, business_slug: "foreign-company" } } }));
  let loginRequests = 0;
  page.on("request", (request) => { if (request.url().endsWith("/auth/login")) loginRequests++; });
  await page.goto("/test2/login");
  await submit(page);
  await expect(page.getByRole("alert")).toContainText("ข้อมูลบริษัทไม่ตรงกับลิงก์");
  expect(loginRequests).toBe(0);
});

test("generic QA login still auto-logins", async ({ page }) => {
  const autoRequests = await mock(page);
  await page.goto("/login");
  await expect(page).toHaveURL(/\/admin$/);
  expect(autoRequests()).toBe(1);
});

test("late generic QA auto-login cannot take over a canonical login", async ({ page }) => {
  await mock(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  let started = false;
  await page.route("**/api/v1/auth/uat/auto-login", async (route) => {
    started = true;
    await pending;
    await route.fulfill({ json: { data: tokens(foreignId, "foreign-company") } });
  });
  await page.goto("/login");
  await expect.poll(() => started).toBe(true);
  await page.evaluate(() => {
    history.pushState({}, "", "/test2/login");
    dispatchEvent(new PopStateEvent("popstate"));
  });
  await expect(page.getByText("เข้าสู่ระบบ · Test Two", { exact: true })).toBeVisible();
  const completed = page.waitForResponse((response) => response.url().endsWith("/auth/uat/auto-login"));
  release();
  await (await completed).finished();
  await expect(page.getByText("กำลังเข้าสู่ระบบทดสอบอัตโนมัติ...")).toHaveCount(0);
  await expect(page).toHaveURL(/\/test2\/login$/);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("erp-auth") || '{"state":{}}').state.accessToken ?? null)).toBeNull();
});
