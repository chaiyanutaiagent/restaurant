import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const companyA = "11111111-1111-4111-8111-111111111111";
// Release acceptance uses the actual signed manifest; Android installer is a bridge fixture.
if (process.env.STORE_RELEASE_MANIFEST) test("UAT9 receives mandatory signed UAT10 update and passes verified artifact to installer", async ({ page }) => {
  const manifest = JSON.parse(readFileSync(process.env.STORE_RELEASE_MANIFEST!, "utf8"));
  expect(manifest.version_code).toBe(10109);
  expect(manifest.minimum_supported_version_code).toBe(10109);
  await page.route("**/downloads/takeaway-store/latest.json", route => route.fulfill({ json: manifest }));
  await page.route("**/src/mobile-store/main.tsx", route => route.fulfill({ contentType: "application/javascript", body: `
    import React from '/node_modules/.vite-mobile-store/deps/react.js';
    import ReactDOM from '/node_modules/.vite-mobile-store/deps/react-dom_client.js';
    import UpdateGate from '/src/mobile-store/UpdateGate.tsx';
    import '/src/index.css';
    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(UpdateGate));
  ` }));
  await page.addInitScript(() => {
    const win = window as unknown as Record<string, unknown>;
    win.androidBridge = {};
    win.Capacitor = {
      PluginHeaders: [{ name: "TakeawayUpdater", methods: [{ name: "getStatus", rtype: "promise" }, { name: "installUpdate", rtype: "promise" }] }],
      nativePromise: async (plugin: string, method: string, options: unknown) => {
        if (plugin !== "TakeawayUpdater") throw new Error("Unexpected native plugin");
        if (method === "getStatus") return { packageId: "com.foodchainservice.takeaway.uat", versionName: "1.1.0-uat.9", versionCode: 10108, installPermission: true };
        if (method === "installUpdate") { win.installerRequest = options; return; }
        throw new Error("Unexpected updater method");
      },
    };
  });
  await page.goto("/");
  const dialog = page.getByRole("dialog", { name: "มีแอปเวอร์ชันใหม่" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("1.1.0-uat.9 → 1.1.0-uat.10");
  await expect(dialog).toContainText("จำเป็นต้องอัปเดตก่อนใช้งานต่อ");
  await expect(dialog.getByRole("button", { name: "ไว้ทีหลัง" })).toHaveCount(0);
  if (process.env.CODEX_VISUAL_QA_PATH) await page.screenshot({ path: process.env.CODEX_VISUAL_QA_PATH.replace(".png", "-update.png") });
  await dialog.getByRole("button", { name: "ดาวน์โหลดและติดตั้ง", exact: true }).click();
  await expect(dialog.getByRole("status")).toContainText("ดาวน์โหลดเสร็จแล้ว");
  expect(await page.evaluate(() => (window as unknown as Record<string, unknown>).installerRequest)).toEqual({ apkUrl: manifest.apk_url, apkSha256: manifest.apk_sha256, versionCode: 10109 });
});
const companyB = "22222222-2222-4222-8222-222222222222";
const branch = "33333333-3333-4333-8333-333333333333";
const brand = "44444444-4444-4444-8444-444444444444";
const permissions = ["takeaway.store.access", "takeaway.catalog.view", "takeaway.stock.view"];
const chamboMenuPermissions = [
  "takeaway.store.access",
  "takeaway.catalog.view",
  "takeaway.sale.create",
  "takeaway.shift.manage",
  "takeaway.stock.view",
  "takeaway.central_order.create",
  "takeaway.transfer.manage",
  "takeaway.credit.manage",
];
function tokens(company: string, device: string, grantedPermissions = permissions) {
  const user = { id: `user-${company}`, company_id: company, username: "stock", display_name: "Store Test", is_superuser: false };
  const payload = { sub: user.id, company_id: company, branch_id: branch, brand_id: brand,
    business_type: "takeaway", target_database: "takeaway", client_surface: "takeaway_store",
    store_device_id: device, station_key: "counter-1", permissions: grantedPermissions, exp: Math.floor(Date.now()/1000)+3600 };
  return { access_token: `test.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.fixture`, refresh_token: `test-refresh-${company}`, user, business_slug: company === companyA ? "company-one" : "company-two" };
}
async function mockApi(page: Page, options: { catalogFailure?: boolean; grantedPermissions?: string[]; writesEnabled?: boolean } = {}) {
  await page.route("https://uat-takeaway.foodchainservice.com/api/v1/**", async (route) => {
    const request = route.request(), url = new URL(request.url());
    let data: unknown = [];
    if (url.pathname.includes("/mobile-store/businesses/")) {
      const code = url.pathname.split("/").pop();
      if (code === "unknown-company" || code === "inactive-company") return route.fulfill({ status: 404, json: { detail: "Business not found" } });
      data = { business_code: code, name: code };
    } else if (url.pathname.endsWith("/mobile-store/branches")) data = [{ id: branch, code: "BKK-01", name: "Branch" }];
    else if (url.pathname.endsWith("/mobile-store/login")) {
      const body = request.postDataJSON(); data = tokens(body.business_code === "company-one" ? companyA : companyB, body.device_id, options.grantedPermissions ?? permissions);
    } else if (url.pathname.endsWith("/takeaway/status")) data = { enabled: true, writes_enabled: options.writesEnabled ?? false, company_id: request.headers()["x-company-id"], branch_id: branch, brand_id: brand, hard_holds: [] };
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
    if (url.pathname.endsWith("/takeaway/shifts")) data = [{ id: "shift-1", status: "open", round_no: 1 }];
    if (url.pathname.endsWith("/takeaway/orders")) data = options.writesEnabled ? [{ id: "queue-1", order_number: "QR-1", total_amount: "58.85", fulfillment_status: url.searchParams.get("fulfillment_status") || "queued" }] : [];
    if (url.pathname.endsWith("/takeaway/sales/offline-sync")) data = { order: { id: "sale-1", order_number: "SALE-1", queue_number: 2, total_amount: "58.85" }, pickup_token: null };
    if (url.pathname.endsWith("/receipt") || url.pathname.endsWith("/receipt/prints")) data = { id: "receipt-1", order_id: "sale-1", receipt_number: "R-1", payload: { items: [{ sku: "CF-001", name: "กาแฟเย็น", quantity: "1", line_total: "55.00" }], subtotal: "55.00", tax_amount: "3.85", total_amount: "58.85", payment_method: "cash" }, issued_at: new Date().toISOString(), print_count: 0 };
    return route.fulfill({ json: { data, meta: {}, error: null } });
  });
}
async function login(page: Page, code: string, destination = "stock") {
  await page.getByLabel("Business Code", { exact: true }).fill(code);
  await page.getByRole("button", { name: "ตรวจสอบบริษัท", exact: true }).click();
  await page.getByLabel("ชื่อผู้ใช้", { exact: true }).fill("stock");
  await page.getByLabel("รหัสผ่าน", { exact: true }).fill("test-fixture-password");
  await page.getByRole("button", { name: "ตรวจสอบบัญชีและสาขา", exact: true }).click();
  await page.getByRole("button", { name: "เข้าใช้งานสาขานี้", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/takeaway/store/${destination}$`));
}

test("Store shell matches the Chambo primary navigation and keeps secondary actions in the drawer", async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 851 });
  await mockApi(page, { grantedPermissions: chamboMenuPermissions });
  await page.goto("/");
  await login(page, "company-one", "sales");

  const primary = page.getByRole("navigation", { name: "เมนูหลักหน้าร้าน" });
  for (const label of ["ขาย", "Stock", "ปิดกะ", "สั่ง/รับสินค้า", "เครดิต"]) {
    await expect(primary.getByRole("link", { name: label, exact: true })).toBeVisible();
  }
  await expect(primary.getByRole("link", { name: "ขาย", exact: true })).toHaveAttribute("aria-current", "page");

  await page.getByRole("button", { name: "เปิดเมนูหน้าร้าน", exact: true }).click();
  const drawer = page.getByRole("complementary", { name: "เมนูหน้าร้าน" });
  for (const label of ["รับออเดอร์", "สินค้า", "Stock หน้าร้าน", "ปิดกะ", "รายการสั่งสินค้า", "แจ้งเติมเครดิต", "รับโอนสินค้า", "ตั้งค่าเครื่องพิมพ์"]) {
    await expect(drawer.getByRole("link", { name: label, exact: true })).toBeVisible();
  }
  await expect(drawer.getByText("ส่วนกลาง", { exact: true })).toHaveCount(0);
  if (process.env.CODEX_VISUAL_QA_PATH) await page.screenshot({ path: process.env.CODEX_VISUAL_QA_PATH, fullPage: true });
});

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
  await page.getByRole("button", { name: "เปิดเมนูหน้าร้าน", exact: true }).click();
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
  await page.getByRole("button", { name: "เปิดเมนูหน้าร้าน", exact: true }).click();
  await page.getByRole("link", { name: "สินค้า", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("โหลดรายการสินค้าไม่สำเร็จ");
  await expect(page.getByRole("button", { name: "ลองใหม่", exact: true })).toBeVisible();
  await expect(page.getByText("ไม่พบสินค้า", { exact: true })).toHaveCount(0);
});

test("logout clears session; same APK resolves and logs into another company", async ({ page }) => {
  await mockApi(page); const requests: string[] = []; page.on("request", (request) => requests.push(request.url()));
  await page.goto("/"); await login(page, "company-one");
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "เปิดเมนูหน้าร้าน", exact: true }).click();
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


test("sales landing, deep link, refresh and back remain distinct from QR queue on Redmi layout", async ({ page }) => {
  await page.setViewportSize({ width: 393, height: 851 });
  await mockApi(page, { grantedPermissions: chamboMenuPermissions, writesEnabled: true });
  await page.goto("/"); await login(page, "company-one", "sales");
  await expect(page.getByTestId("takeaway-sales-workspace")).toBeVisible();
  await expect(page.getByRole("heading", { name: "รายการเตรียมและส่งมอบ" })).toHaveCount(0);
  await expect(page.getByRole("banner")).toContainText("company-one");
  await expect(page.getByText(/BKK-01 · Branch/)).toBeVisible();
  await page.getByRole("button", { name: "เพิ่ม กาแฟเย็น", exact: true }).click();
  await expect(page.getByLabel("จำนวน กาแฟเย็น")).toHaveText("1");
  await page.getByRole("button", { name: "ลด กาแฟเย็น", exact: true }).click();
  await expect(page.getByLabel("จำนวน กาแฟเย็น")).toHaveText("0");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "เปิดเมนูหน้าร้าน", exact: true }).click();
  await page.getByRole("link", { name: "รับออเดอร์", exact: true }).click();
  await expect(page).toHaveURL(/\/takeaway\/store\/orders$/);
  await expect(page.getByRole("heading", { name: "รายการเตรียมและส่งมอบ" })).toBeVisible();
  await expect(page.getByTestId("sales-product")).toHaveCount(0);
  await page.goBack();
  await expect(page).toHaveURL(/\/takeaway\/store\/sales$/);
  await page.reload();
  await expect(page.getByTestId("takeaway-sales-workspace")).toBeVisible();
  await page.goto("/takeaway/store/orders");
  await expect(page.getByTestId("takeaway-orders-workspace")).toBeVisible();
  await page.getByRole("navigation", { name: "เมนูหลักหน้าร้าน" }).getByRole("link", { name: "ขาย", exact: true }).click();
  await expect(page.getByTestId("takeaway-sales-workspace")).toBeVisible();
  if (process.env.CODEX_VISUAL_QA_PATH) await page.screenshot({ path: process.env.CODEX_VISUAL_QA_PATH.replace(".png", "-sales.png"), fullPage: true });
});

for (const method of ["cash", "other"]) test(`sales records ${method} with server price IDs and explicit external-payment confirmation`, async ({ page }) => {
  await mockApi(page, { grantedPermissions: chamboMenuPermissions, writesEnabled: true });
  await page.goto("/"); await login(page, "company-one", "sales");
  await page.getByRole("button", { name: "เพิ่ม กาแฟเย็น", exact: true }).click();
  const pay = page.getByRole("button", { name: "บันทึกการรับชำระ", exact: true });
  if (method === "other") {
    await page.getByLabel("โอน/ชำระภายนอก (ตรวจรับเอง)", { exact: true }).check();
    await expect(pay).toBeDisabled();
    await page.getByLabel("เลขอ้างอิงการรับเงิน", { exact: true }).fill("UAT-EXTERNAL-1");
    await page.getByLabel("ตรวจสอบว่าได้รับเงินจริงแล้ว").check();
  }
  const sent = page.waitForRequest((r) => r.url().endsWith("/takeaway/sales/offline-sync") && r.method() === "POST");
  await pay.click();
  const payload = (await sent).postDataJSON();
  expect(payload.payment.method).toBe(method);
  expect(payload.payment.amount).toBe("58.85");
  expect(payload.items).toEqual([{ catalog_item_id: "item-coffee", quantity: "1" }]);
  expect(payload.idempotency_key).toMatch(/^takeaway-sale:/);
  await expect(page.getByLabel("จำนวน กาแฟเย็น")).toHaveText("0");
  await expect(page.getByRole("button", { name: "ใบลูกค้า", exact: true })).toBeEnabled();
  if (method === "cash") {
    await page.getByRole("button", { name: "ใบลูกค้า", exact: true }).click();
    await expect(page.getByText("กระดาษออกครบแล้วหรือไม่?")).toBeVisible();
    const recorded = page.waitForRequest(r => r.url().endsWith("/receipt/prints") && r.method() === "POST");
    await page.getByRole("button", { name: "ยืนยันพิมพ์แล้ว", exact: true }).click();
    expect((await recorded).postDataJSON().copy_type).toBe("customer");
  }
});

test("cash sale stays on device while offline, then syncs on reconnect", async ({ page, context }) => {
  await mockApi(page, { grantedPermissions: chamboMenuPermissions, writesEnabled: true });
  await page.goto("/"); await login(page, "company-one", "sales");
  await page.getByRole("button", { name: "เพิ่ม กาแฟเย็น", exact: true }).click();
  await context.setOffline(true);
  await page.getByRole("button", { name: "บันทึกการรับชำระ", exact: true }).click();
  await expect(page.getByText(/รายการในเครื่อง: รอส่ง 1/)).toBeVisible();
  await expect(page.getByRole("button", { name: "ใบลูกค้า", exact: true })).toBeEnabled();
  const synced = page.waitForRequest(r => r.url().endsWith("/takeaway/sales/offline-sync") && r.method() === "POST");
  await context.setOffline(false);
  expect((await synced).postDataJSON().payment.method).toBe("cash");
  await expect(page.getByText(/รายการในเครื่อง: รอส่ง 1/)).toHaveCount(0);
});

test("offline sale retry reuses the same idempotency key after a lost response", async ({ page }) => {
  await mockApi(page, { grantedPermissions: chamboMenuPermissions, writesEnabled: true });
  const keys: string[] = [];
  let failing = true;
  await page.route("**/takeaway/sales/offline-sync", async route => {
    keys.push(route.request().postDataJSON().idempotency_key);
    if (failing) return route.abort("failed");
    return route.fulfill({ json: { data: { order: { id: "sale-1", order_number: "SALE-1", queue_number: 2 }, pickup_token: null } } });
  });
  await page.goto("/"); await login(page, "company-one", "sales");
  await page.getByRole("button", { name: "เพิ่ม กาแฟเย็น", exact: true }).click();
  await page.getByRole("button", { name: "บันทึกการรับชำระ", exact: true }).click();
  await expect(page.getByText(/รายการในเครื่อง: รอส่ง 1/)).toBeVisible();
  failing = false;
  await page.getByRole("button", { name: "ส่งรายการค้าง", exact: true }).click();
  await expect.poll(() => keys.length).toBe(2);
  expect(keys[0]).toBe(keys[1]);
  await expect(page.getByText(/รายการในเครื่อง: รอส่ง 1/)).toHaveCount(0);
});
