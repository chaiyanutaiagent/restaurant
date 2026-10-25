import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { BinaryBitmap, HybridBinarizer, QRCodeReader, RGBLuminanceSource } from "@zxing/library";
const { PNG } = createRequire(import.meta.url)("pngjs");

test("Mini Mart admin can register Counter, pair, and reach Retail sales link", async ({ page }) => {
  const company = "11111111-1111-4111-8111-111111111111";
  const branch = "22222222-2222-4222-8222-222222222222";
  const brand = "33333333-3333-4333-8333-333333333333";
  const device = { device_id: company, company_id: company, branch_id: branch, brand_id: brand,
    name: "macbook", device_code: "C-TEST123456", device_type: "counter", station_key: null,
    business_type: "retail_pos", target_database: "retail_pos", credential_version: 1,
    paired_at: new Date().toISOString(), last_seen_at: new Date().toISOString() };
  const session = { access_token: "fixture-device", refresh_token: "fixture-refresh", expires_in: 3600, device };
  await page.addInitScript(({ company, branch, brand }) => {
    localStorage.setItem("erp-auth", JSON.stringify({ state: { accessToken: "fixture-staff", refreshToken: "fixture-staff-refresh",
      companyId: company, branchId: branch, brandId: brand, businessType: "retail_pos", targetDatabase: "retail_pos",
      permissions: ["system.device.view", "system.device.manage", "pos.sale.create"], scopeTypes: ["branch"],
      user: { id: company, company_id: company, username: "loft.admin", is_active: true } }, version: 0 }));
  }, { company, branch, brand });
  let creates = 0, pairs = 0, restaurantSettings = 0;
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const ok = (data: unknown) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ data, meta: {}, error: null }) });
    if (path.endsWith("/system/branches")) return ok([{ id: branch, company_id: company, brand_id: brand, code: "TLM-01", name: "The Loft Mini Mart", business_type: "retail_pos", target_database: "retail_pos" }]);
    if (path.endsWith("/settings")) { restaurantSettings++; return ok({}); }
    if (path.endsWith("/system/devices") && route.request().method() === "POST") {
      creates++;
      expect(route.request().postDataJSON()).toMatchObject({ branch_id: branch, device_type: "counter", name: "macbook" });
      return ok({ device: { ...device, id: device.device_id }, pairing_pin: "123456", pairing_expires_at: new Date(Date.now() + creates * 600000).toISOString(),
        pairing_qr_payload: `restaurant-pos://pair?company_id=${company}&device_code=${device.device_code}&pin=123456` });
    }
    if (path.endsWith("/device-auth/pair")) {
      pairs++;
      expect(route.request().postDataJSON()).toEqual({ company_id: company, device_code: device.device_code, pairing_pin: "123456" });
      return ok(session);
    }
    if (path.endsWith("/device-auth/renew")) return ok(session);
    if (path.endsWith("/device-workspaces/counter/bootstrap")) return ok({ device, branch: { id: branch, code: "TLM-01", name: "The Loft Mini Mart" }, requires_staff_login: true });
    return ok([]);
  });
  await page.goto("/devices");
  await expect(page.getByLabel("สาขา", { exact: true })).toHaveValue(branch);
  await page.getByLabel("ประเภท", { exact: true }).selectOption("kitchen");
  await expect(page.getByRole("button", { name: "สร้าง Device และ PIN" })).toBeDisabled();
  await page.getByLabel("ประเภท", { exact: true }).selectOption("counter");
  await page.getByLabel("ชื่อเครื่อง", { exact: true }).fill("macbook");
  await page.getByRole("button", { name: "สร้าง Device และ PIN" }).click();
  await expect(page.getByRole("button", { name: "แชร์รูป QR", exact: true })).toBeEnabled();
  // Unsupported native file sharing falls back to downloading the PNG.
  await page.evaluate(() => Object.defineProperty(navigator, "canShare", { configurable: true, value: () => false }));
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "แชร์รูป QR", exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("foodchainservice-pair-C-TEST123456.png");
  const png = PNG.sync.read(readFileSync((await download.path())!));
  const pixels = new Int32Array(png.width * png.height);
  for (let i = 0; i < pixels.length; i++) pixels[i] = (png.data[i * 4] << 16) | (png.data[i * 4 + 1] << 8) | png.data[i * 4 + 2];
  const decoded = new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(pixels, png.width, png.height)))).getText();
  const qr = new URL(decoded);
  expect(qr.pathname).toBe("/device/pair/retail");
  expect(qr.searchParams.get("company_id")).toBe(company);
  expect(qr.searchParams.get("device_code")).toBe(device.device_code);
  expect(qr.searchParams.get("pin")).toBe("123456");
  expect(qr.searchParams.get("target_app")).toBe("retail");
  expect(qr.searchParams.get("branch_id")).toBe(branch);
  await expect(page.getByRole("link", { name: "เปิดแอป Retail บน Android" })).toHaveAttribute("href", /scheme=foodchainservice-retail-uat;package=com\.foodchainservice\.retail\.uat;/);
  // Validate the share payload without actually sending anything externally.
  await page.evaluate(() => {
    Object.defineProperty(navigator, "canShare", { configurable: true, value: () => true });
    Object.defineProperty(navigator, "share", { configurable: true, value: async (data: ShareData) => {
      (window as unknown as { shareResult: unknown }).shareResult = { name: data.files?.[0].name, type: data.files?.[0].type, size: data.files?.[0].size, text: data.text };
    } });
  });
  await page.getByRole("button", { name: "แชร์รูป QR", exact: true }).click();
  const shared = await page.evaluate(() => (window as unknown as { shareResult: { name: string; type: string; size: number; text: string } }).shareResult);
  expect(shared.name).toBe("foodchainservice-pair-C-TEST123456.png");
  expect(shared.type).toBe("image/png");
  expect(shared.size).toBeGreaterThan(100);
  expect(shared.text).toContain("หมดอายุ");
  await page.evaluate(() => Object.defineProperty(navigator, "share", { configurable: true, value: async () => { throw new DOMException("cancelled", "AbortError"); } }));
  await page.getByRole("button", { name: "แชร์รูป QR", exact: true }).click();
  await expect(page.getByText("แชร์รูปไม่ได้ กรุณากดดาวน์โหลด QR แล้วแนบรูปส่งเอง")).toHaveCount(0);
  await page.evaluate(() => Object.defineProperty(navigator, "share", { configurable: true, value: async () => { throw new Error("blocked"); } }));
  await page.getByRole("button", { name: "แชร์รูป QR", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "แชร์รูปไม่ได้" })).toBeVisible();
  // Move the browser clock beyond the credential expiry; don't change server time.
  await page.clock.install();
  await page.clock.fastForward(601000);
  await expect(page.getByRole("button", { name: "แชร์รูป QR", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "ดาวน์โหลด QR", exact: true })).toBeDisabled();
  await expect(page.getByAltText("QR สำหรับจับคู่อุปกรณ์")).toHaveCount(0);
  // A second mocked provisioning response supplies a fresh PIN window.
  await page.getByLabel("ชื่อเครื่อง", { exact: true }).fill("macbook");
  await page.getByRole("button", { name: "สร้าง Device และ PIN" }).click();
  const pairingHref = new URL((await page.getByRole("link", { name: "เปิดหน้าจับคู่เครื่องนี้" }).getAttribute("href"))!);
  await page.goto(pairingHref.pathname + pairingHref.search);
  await expect(page.getByText("ใช้งานผ่านเบราว์เซอร์บนเครื่องนี้ได้เลย ไม่ต้องติดตั้งแอป")).toBeVisible();
  await page.getByRole("button", { name: "จับคู่และเปิด Workspace" }).click();
  await expect(page.getByRole("link", { name: "เปิดหน้าขาย", exact: true })).toHaveAttribute("href", "/retail/pos");
  expect(creates).toBe(2);
  expect(pairs).toBe(1);
  expect(restaurantSettings).toBe(0);
});
