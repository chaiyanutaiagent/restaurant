import { test, expect, type Page } from "@playwright/test";

const companyA = "11111111-1111-4111-8111-111111111111";
const companyB = "22222222-2222-4222-8222-222222222222";
const branch = "33333333-3333-4333-8333-333333333333";
const brand = "44444444-4444-4444-8444-444444444444";
const permissions = ["takeaway.store.access", "takeaway.catalog.view", "takeaway.stock.view"];
function tokens(company: string, device: string) {
  const user = { id: `user-${company}`, company_id: company, username: "stock", display_name: "Store Test", is_superuser: false };
  const payload = { sub: user.id, company_id: company, branch_id: branch, brand_id: brand,
    business_type: "takeaway", target_database: "takeaway", client_surface: "takeaway_store",
    store_device_id: device, station_key: "counter-1", permissions, exp: Math.floor(Date.now()/1000)+3600 };
  return { access_token: `test.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.fixture`, refresh_token: `test-refresh-${company}`, user, business_slug: company === companyA ? "company-one" : "company-two" };
}
async function mockApi(page: Page, options: { catalogFailure?: boolean } = {}) {
  await page.route("https://uat-takeaway.foodchainservice.com/api/v1/**", async (route) => {
    const request = route.request(), url = new URL(request.url());
    let data: unknown = [];
    if (url.pathname.includes("/mobile-store/businesses/")) {
      const code = url.pathname.split("/").pop();
      if (code === "unknown-company" || code === "inactive-company") return route.fulfill({ status: 404, json: { detail: "Business not found" } });
      data = { business_code: code, name: code };
    } else if (url.pathname.endsWith("/mobile-store/branches")) data = [{ id: branch, code: "BKK-01", name: "Branch" }];
    else if (url.pathname.endsWith("/mobile-store/login")) {
      const body = request.postDataJSON(); data = tokens(body.business_code === "company-one" ? companyA : companyB, body.device_id);
    } else if (url.pathname.endsWith("/takeaway/status")) data = { enabled: true, writes_enabled: false, company_id: request.headers()["x-company-id"], branch_id: branch, brand_id: brand, hard_holds: [] };
    else if (url.pathname.endsWith("/takeaway/catalog/categories")) data = [{ id: "category-drink", name: "เครื่องดื่ม" }];
    else if (url.pathname.endsWith("/takeaway/catalog/items")) {
      if (options.catalogFailure) return route.fulfill({ status: 500, json: { detail: "catalog unavailable" } });
      data = [{
      item: { id: "item-coffee", brand_id: brand, category_id: "category-drink", sku: "CF-001", barcode: "885000000001",
        name: "กาแฟเย็น", description: "หวานน้อย", image_url: null, price: "55.00", unit: "แก้ว", tax_rate: "7.00",
        kitchen_station: "drink", track_stock: true, sort_order: 1, is_featured: true, is_active: true },
      effective_price: "55.00", branch_is_available: true, available_qty: "8.00", is_available: true,
      }];
    }
    return route.fulfill({ json: { data, meta: {}, error: null } });
  });
}
async function login(page: Page, code: string) {
  await page.getByLabel("Business Code", { exact: true }).fill(code);
  await page.getByRole("button", { name: "ตรวจสอบบริษัท", exact: true }).click();
  await page.getByLabel("ชื่อผู้ใช้", { exact: true }).fill("stock");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("test-fixture-password");
  await page.getByRole("button", { name: "ตรวจสอบบัญชีและสาขา", exact: true }).click();
  await page.getByRole("button", { name: "เข้าใช้งานสาขานี้", exact: true }).click();
  await expect(page).toHaveURL(/\/takeaway\/store\/stock$/);
}

test("manual forbidden URLs are denied before and after login", async ({ page }) => {
  await mockApi(page);
  for (const path of ["/restaurant", "/retail", "/platform", "/takeaway/central/orders", "/takeaway/admin/users", "/admin", "/takeaway/store/../central/orders"]) {
    await page.goto(path); await expect(page.getByRole("heading", { name: "ไม่อนุญาตให้เข้าหน้านี้" })).toBeVisible();
  }
  await page.goto("/"); await login(page, "company-one");
  await page.goto("/takeaway/store/credits"); await expect(page.getByRole("alert")).toHaveText("ไม่มีสิทธิ์ใช้งานหน้านี้");
  await page.goto("/takeaway/central/orders"); await expect(page.getByRole("heading", { name: "ไม่อนุญาตให้เข้าหน้านี้" })).toBeVisible();
});

test("unknown and inactive business codes cannot progress", async ({ page }) => {
  await mockApi(page); await page.goto("/");
  for (const code of ["unknown-company", "inactive-company"]) {
    await page.getByLabel("Business Code", { exact: true }).fill(code);
    await page.getByRole("button", { name: "ตรวจสอบบริษัท", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByLabel("รหัสผ่าน", { exact: true })).toHaveCount(0);
  }
});

test("Store product list shows customer-facing content and actual branch stock", async ({ page }) => {
  await mockApi(page); await page.goto("/"); await login(page, "company-one");
  await page.getByRole("link", { name: "สินค้า", exact: true }).click();
  await expect(page).toHaveURL(/\/takeaway\/store\/catalog$/);
  await expect(page.getByRole("heading", { name: "รายการสินค้า", exact: true })).toBeVisible();
  await expect(page.getByText("กาแฟเย็น", { exact: true })).toBeVisible();
  await expect(page.getByText("หวานน้อย", { exact: true })).toBeVisible();
  await expect(page.getByText("พร้อมขาย 8", { exact: true })).toBeVisible();
  await page.getByPlaceholder("ค้นหาชื่อสินค้า SKU หรือบาร์โค้ด").fill("ไม่พบ");
  await expect(page.getByText("ไม่พบสินค้า", { exact: true })).toBeVisible();
});

test("Store product list reports API failure instead of pretending the catalog is empty", async ({ page }) => {
  await mockApi(page, { catalogFailure: true }); await page.goto("/"); await login(page, "company-one");
  await page.getByRole("link", { name: "สินค้า", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("โหลดรายการสินค้าไม่สำเร็จ");
  await expect(page.getByRole("button", { name: "ลองใหม่", exact: true })).toBeVisible();
  await expect(page.getByText("ไม่พบสินค้า", { exact: true })).toHaveCount(0);
});

test("logout clears session; same APK resolves and logs into another company", async ({ page }) => {
  await mockApi(page); const requests: string[] = []; page.on("request", (request) => requests.push(request.url()));
  await page.goto("/"); await login(page, "company-one");
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "ออกจากระบบ / เปลี่ยนบริษัท", exact: true }).click();
  await expect(page.getByLabel("Business Code", { exact: true })).toHaveValue("");
  expect(await page.evaluate(() => localStorage.getItem("erp-auth"))).toBeNull();
  await login(page, "company-two");
  await expect(page.getByRole("banner")).toContainText("company-two");
  expect(requests.some((url) => url.includes("auto-login"))).toBe(false);
});

test("restricted Store token accepts UAT superadmin identity but still rejects wildcard", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async ({ company, fixture }) => {
    const session = await import("/src/mobile-store/session.ts");
    const restricted = { ...fixture, user: { ...fixture.user, is_superuser: true } };
    let restrictedAccepted = true;
    try { await session.saveSession({ tokens: restricted, companyId: company, deviceId: "device" }); }
    catch { restrictedAccepted = false; }
    const parts = fixture.access_token.split(".");
    const claims = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
    const encoded = btoa(JSON.stringify({ ...claims, permissions: ["*"] }))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    let wildcardDenied = false;
    try {
      await session.saveSession({
        tokens: { ...restricted, access_token: `${parts[0]}.${encoded}.${parts[2]}` },
        companyId: company,
        deviceId: "device",
      });
    } catch { wildcardDenied = true; }
    await session.clearSession();
    return { restrictedAccepted, wildcardDenied };
  }, { company: companyA, fixture: tokens(companyA, "device") });
  expect(result).toEqual({ restrictedAccepted: true, wildcardDenied: true });
});

test("offline data is isolated across companies and logout preserves unsynced sales", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async ({ a, b, tA, tB, branchId, brandId }) => {
    const sessionPath = "/src/mobile-store/session.ts", dbPath = "/src/mobile-store/db.ts", offlinePath = "/src/lib/takeawayOffline.ts";
    const session = await import(sessionPath), { db, cleanupStoreData } = await import(dbPath), offline = await import(offlinePath);
    for (const company of [a, b]) await db.takeawayPendingSales.put({ client_sale_id: company, company_id: company,
      branch_id: branchId, brand_id: brandId, user_id: `user-${company}`, status: company === a ? "pending" : "synced", created_at: 1, updated_at: 1 });
    await session.saveSession({ tokens: tA, companyId: a, deviceId: "device" });
    const first = await offline.getTakeawayOutboxSummary();
    let receiptDenied = false, logoutBlocked = false;
    try { await offline.markTakeawayReceiptPrinted(b, "local:other", "customer"); } catch { receiptDenied = true; }
    try { await cleanupStoreData(); } catch { logoutBlocked = true; }
    await session.saveSession({ tokens: tB, companyId: b, deviceId: "device" });
    const second = await offline.getTakeawayOutboxSummary();
    await db.takeawayPendingSales.update(a, { status: "synced" });
    await cleanupStoreData(); await session.clearSession();
    return { first, second, receiptDenied, logoutBlocked, rows: await db.takeawayPendingSales.count(), token: session.useAuthStore.getState().accessToken };
  }, { a: companyA, b: companyB, tA: tokens(companyA, "device"), tB: tokens(companyB, "device"), branchId: branch, brandId: brand });
  expect(result.first.pending).toBe(1); expect(result.second.pending).toBe(0);
  expect(result.receiptDenied).toBe(true); expect(result.logoutBlocked).toBe(true);
  expect(result.rows).toBe(0); expect(result.token).toBeNull();
});

test("business QR accepts code only and never navigates to arbitrary URLs", async ({ page }) => {
  await page.goto("/");
  const values = await page.evaluate(async () => {
    const path = "/src/mobile-store/routes.ts", { businessCodeFromQr } = await import(path);
    const valid = businessCodeFromQr("foodchainservice://business/company-two");
    let denied = 0;
    for (const value of ["https://attacker.example/login", "javascript:alert(1)", "../admin", "foodchainservice://business/a/b"]) {
      try { businessCodeFromQr(value); } catch { denied++; }
    }
    return { valid, denied };
  });
  expect(values).toEqual({ valid: "company-two", denied: 4 });
});

test("old responses and failed refresh cannot replace or clear a new employee session", async ({ page }) => {
  await page.goto("/not-a-store-route");
  await expect(page.getByRole("heading", { name: "ไม่อนุญาตให้เข้าหน้านี้" })).toBeVisible();
  const result = await page.evaluate(async ({ a, b, tA, tB }) => {
    const sessionPath = "/src/mobile-store/session.ts", apiPath = "/src/mobile-store/api.ts";
    const session = await import(sessionPath), { default: api, onboardingApi } = await import(apiPath);
    const save = (company: string, tokens: unknown) => session.saveSession({ tokens, companyId: company, deviceId: "device" });
    await save(a, tA);
    let finish!: () => void, started!: () => void;
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    const entered = new Promise<void>((resolve) => { started = resolve; });
    api.defaults.adapter = async (config: unknown) => { started(); await pending; return { data: {}, status: 200, statusText: "OK", headers: {}, config }; };
    const oldRequest = api.get("/takeaway/status").then(() => false, () => true);
    await entered; await save(b, tB); finish();
    const staleDenied = await oldRequest;
    await save(a, tA);
    let refreshFinish!: () => void, refreshStarted!: () => void;
    const refreshPending = new Promise<void>((resolve) => { refreshFinish = resolve; });
    const refreshEntered = new Promise<void>((resolve) => { refreshStarted = resolve; });
    api.defaults.adapter = async (config: unknown) => { throw { isAxiosError: true, response: { status: 401 }, config }; };
    onboardingApi.defaults.adapter = async (config: unknown) => { refreshStarted(); await refreshPending; throw { isAxiosError: true, response: { status: 401 }, config }; };
    const oldRefresh = api.get("/takeaway/status").catch(() => null);
    await refreshEntered; await save(b, tB); refreshFinish(); await oldRefresh;
    return { staleDenied, company: session.useAuthStore.getState().companyId, user: session.useAuthStore.getState().user.id };
  }, { a: companyA, b: companyB, tA: tokens(companyA, "device"), tB: tokens(companyB, "device") });
  expect(result).toEqual({ staleDenied: true, company: companyB, user: `user-${companyB}` });
});

test("Store updater rejects an unconfigured or unverified release channel", async ({ page }) => {
  await page.goto("/");
  const denied = await page.evaluate(async () => {
    const path = "/src/mobile-store/appUpdate.ts", { loadTakeawayRelease } = await import(path);
    try { await loadTakeawayRelease(); return false; } catch { return true; }
  });
  expect(denied).toBe(true);
});

test("session rejects a mixed-company or mixed-user login response", async ({ page }) => {
  await page.goto("/");
  const denied = await page.evaluate(async ({ fixture, company }) => {
    const path = "/src/mobile-store/session.ts", { sessionClaims } = await import(path);
    let count = 0;
    for (const user of [{ ...fixture.user, company_id: "another-company" }, { ...fixture.user, id: "another-user" }]) {
      try { sessionClaims({ tokens: { ...fixture, user }, companyId: company, deviceId: "device" }); }
      catch { count++; }
    }
    return count;
  }, { fixture: tokens(companyA, "device"), company: companyA });
  expect(denied).toBe(2);
});

test("onboarding rejects valid-looking tokens for a different business code", async ({ page }) => {
  await mockApi(page);
  await page.route("**/mobile-store/login", async (route) => {
    const body = route.request().postDataJSON();
    await route.fulfill({ json: { data: tokens(companyB, body.device_id), meta: {}, error: null } });
  });
  await page.goto("/");
  await page.getByLabel("Business Code", { exact: true }).fill("company-one");
  await page.getByRole("button", { name: "ตรวจสอบบริษัท", exact: true }).click();
  await page.getByLabel("ชื่อผู้ใช้", { exact: true }).fill("stock");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("fixture-only");
  await page.getByRole("button", { name: "ตรวจสอบบัญชีและสาขา", exact: true }).click();
  await page.getByRole("button", { name: "เข้าใช้งานสาขานี้", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("เข้าสู่ระบบไม่สำเร็จ");
  expect(await page.evaluate(async () => {
    const path = "/src/mobile-store/session.ts";
    return (await import(path)).useAuthStore.getState().companyId;
  })).toBeNull();
});

test("Store updater accepts only the matching signed manifest payload", async ({ page }) => {
  await page.goto("/");
  const result = await page.evaluate(async () => {
    const path = "/src/mobile-store/appUpdate.ts";
    const { verifyTakeawayStoreReleaseManifest } = await import(path);
    const keys = await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
    const publicKey = await crypto.subtle.exportKey("spki", keys.publicKey);
    const pem = `-----BEGIN PUBLIC KEY-----\n${btoa(String.fromCharCode(...new Uint8Array(publicKey)))}\n-----END PUBLIC KEY-----`;
    const manifest = {
      surface: "takeaway_store" as const,
      channel: "uat" as const,
      package_id: "com.foodchainservice.takeaway.uat",
      version_name: "1.1.0-uat.fixture",
      version_code: 10104,
      minimum_supported_version_code: 10103,
      rollback_version_code: 10103,
      apk_url: "https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/fixture.apk",
      apk_sha256: "a".repeat(64),
      published_at: "2026-09-29T00:00:00.000Z",
      signature: "",
    };
    const payload = JSON.stringify({
      apk_sha256: manifest.apk_sha256, apk_url: manifest.apk_url, channel: manifest.channel,
      minimum_supported_version_code: manifest.minimum_supported_version_code, package_id: manifest.package_id,
      published_at: manifest.published_at, rollback_version_code: manifest.rollback_version_code,
      surface: manifest.surface, version_code: manifest.version_code, version_name: manifest.version_name,
    });
    const signature = await crypto.subtle.sign({ name: "Ed25519" }, keys.privateKey, new TextEncoder().encode(payload));
    manifest.signature = btoa(String.fromCharCode(...new Uint8Array(signature)));
    const valid = await verifyTakeawayStoreReleaseManifest(manifest, pem);
    const tampered = await verifyTakeawayStoreReleaseManifest({ ...manifest, version_code: 10105 }, pem);
    return { valid, tampered };
  });
  expect(result).toEqual({ valid: true, tampered: false });
});
