import { expect, test, type Page } from "@playwright/test";
import { BUSINESS_DOCUMENTS, DOCUMENT_CENTER_PERMISSIONS, filterBusinessDocuments, payableDocumentTab, visibleBusinessDocuments } from "../src/config/businessDocuments";

const companyId = "11111111-1111-4111-8111-111111111111";
const branchId = "22222222-2222-4222-8222-222222222222";
const user = { id: "33333333-3333-4333-8333-333333333333", company_id: companyId, username: "documents.test", display_name: "Document Tester", is_active: true, is_superuser: false };

async function setup(page: Page, permissions = DOCUMENT_CENTER_PERMISSIONS, options: { contextStatus?: number; mismatch?: boolean; delay?: number; registerMismatch?: boolean; registerStatus?: number } = {}): Promise<string[]> {
  const writes: string[] = [];
  await page.addInitScript(({ companyId, branchId, user, permissions }) => {
    localStorage.setItem("erp-auth", JSON.stringify({ state: {
      accessToken: "local-documents-test", refreshToken: "local-refresh", user,
      companyId, branchId, permissions, scopeTypes: ["company", "branch"],
      brandId: null, stationKey: null, businessType: "restaurant", targetDatabase: "restaurant",
    }, version: 0 }));
  }, { companyId, branchId, user, permissions });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    if (request.method() !== "GET") writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
    const path = new URL(request.url()).pathname;
    let data: unknown = [];
    if (path.endsWith("/company/context")) {
      if (options.delay) await new Promise((resolve) => setTimeout(resolve, options.delay));
      if (options.contextStatus) return route.fulfill({ status: options.contextStatus, json: { detail: "Context unavailable" } });
      data = {
        contract_version: "2026-09-19.1", environment: "uat",
        company: { id: options.mismatch ? "other-company" : companyId, code: "DOC", name: "บริษัททดสอบเอกสาร" },
        brand: null, branch: { id: branchId, code: "BKK-01", name: "สาขาทดสอบ" },
        business_type: "restaurant", target_database: "restaurant", currency: "THB", timezone: "Asia/Bangkok",
        tax: { configured: false }, all_scope_allowed: { brand: true, branch: true, station: false },
        updated_at: new Date().toISOString(),
      };
    } else if (path.endsWith("/company/documents/register")) {
      if (options.registerStatus) return route.fulfill({ status: options.registerStatus, json: { detail: "Denied" } });
      const params = new URL(request.url()).searchParams;
      const pageNumber = Number(params.get("page") ?? 1);
      data = {
        items: params.get("search") === "missing" ? [] : [{ id: "doc-1", number: pageNumber === 1 ? "DOC-001" : "DOC-002", document_date: "2026-10-13", amount: "1070.00", status: "issued", created_at: "2026-10-13T00:00:00Z" }],
        has_more: pageNumber === 1, company_id: options.registerMismatch ? "other-company" : companyId, branch_id: branchId,
        source: "accounting_legacy", historical_snapshot: false,
      };
    } else if (path.endsWith("/history")) {
      data = { company_id: companyId, branch_id: branchId, number: "DOC-001", status: "approved", original_available: true,
        snapshot: { captured_at: "2026-10-13T00:00:00Z", captured_by: user.id, sha256: "a".repeat(64), template_version: "document-lifecycle-1" },
        events: [{ sequence: 2, action: "draft_revised", actor_id: user.id, occurred_at: "2026-10-13T00:00:00Z", reason: "แก้ไขจำนวน", payload: { before: 2, after: 3 } }],
        legacy_audit: [], has_more: false, correction_policy: "เอกสารออกแล้วห้ามแก้ทับ" };
    } else if (path.endsWith("/company/action-center")) {
      data = { items: [], total: 0, unread: 0, generated_at: new Date().toISOString() };
    }
    return route.fulfill({ json: { data, meta: { version: "test", total: 0 }, error: null } });
  });
  return writes;
}

test("catalog permissions, filters and tab allowlist are explicit", () => {
  expect(visibleBusinessDocuments([])).toEqual([]);
  expect(visibleBusinessDocuments(["pos.sale.create", "system.company.edit"])).toEqual([]);
  expect(visibleBusinessDocuments(["inventory.purchase.view"]).map((entry) => entry.id)).toEqual(["purchase_order", "goods_receipt"]);
  expect(visibleBusinessDocuments(["*"])).toHaveLength(11);
  expect(new Set(BUSINESS_DOCUMENTS.map((entry) => entry.id)).size).toBe(11);
  for (const entry of BUSINESS_DOCUMENTS) {
    expect(entry.route).toMatch(/^\/(?!\/)/);
    expect(DOCUMENT_CENTER_PERMISSIONS).toContain(entry.permission);
  }
  expect(filterBusinessDocuments(BUSINESS_DOCUMENTS, "  ใบสำคัญจ่าย  ", "payable").map((entry) => entry.id)).toEqual(["payment_voucher"]);
  expect(filterBusinessDocuments(BUSINESS_DOCUMENTS, "ไม่พบแน่นอน", "all")).toEqual([]);
  expect(payableDocumentTab("wht")).toBe("wht");
  expect(payableDocumentTab("payments")).toBe("payments");
  expect(payableDocumentTab("https://example.com")).toBe("invoices");
  expect(payableDocumentTab(null)).toBe("invoices");
});

test("history on tablet is scoped, shows revision and does not print automatically", async ({ page, context }, testInfo) => {
  const writes = await setup(page);
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/company/documents");
  await page.getByRole("button", { name: "DOC-001", exact: true }).click();
  const history = page.getByRole("region", { name: "ประวัติเอกสาร", exact: true });
  await expect(history).toContainText("แก้ไขจำนวน");
  await expect(history.getByRole("button", { name: "ดาวน์โหลดต้นฉบับครั้งแรก" })).toBeEnabled();
  await history.getByText("ข้อมูลที่บันทึกในรุ่นนี้", { exact: true }).click();
  await expect(history).toContainText('"before": 2');
  expect(await history.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("document-history-tablet.png"), animations: "disabled" });
  expect(writes).toEqual([]);
  await context.setOffline(true);
  await expect(history).toContainText("ออฟไลน์");
  await expect(history.getByRole("button", { name: "ดาวน์โหลดสำเนา" })).toHaveCount(0);
});

test("history mismatch hides all evidence and export buttons", async ({ page }) => {
  await setup(page);
  await page.route("**/company/documents/*/*/history*", route => route.fulfill({ json: { data: {
    company_id: "other", branch_id: branchId, number: "PRIVATE-DOC", snapshot: { sha256: "private" }, events: []
  } } }));
  await page.goto("/company/documents");
  await page.getByRole("button", { name: "DOC-001", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("บริบทไม่ตรง");
  await expect(page.getByText("PRIVATE-DOC")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "ดาวน์โหลดสำเนา" })).toHaveCount(0);
});

test("desktop and tablet expose eleven source links without creating transactions", async ({ page }, testInfo) => {
  const writes = await setup(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/company/documents");
  await expect(page.getByRole("heading", { name: "ศูนย์เอกสาร", exact: true })).toBeVisible();
  await expect(page.getByTestId("company-documents")).toContainText("บริษัททดสอบเอกสาร");
  await expect(page.locator("article[data-testid^='document-']")).toHaveCount(11);
  for (const entry of BUSINESS_DOCUMENTS) {
    await expect(page.getByTestId(`document-${entry.id}`).getByRole("link")).toHaveAttribute("href", entry.route);
  }
  for (const size of [{ width: 1440, height: 900 }, { width: 820, height: 1180 }, { width: 1024, height: 768 }]) {
    await page.setViewportSize(size);
    if (size.width < 1280) {
      await expect.poll(() => page.locator("aside").evaluate((node) => node.getBoundingClientRect().right)).toBeLessThanOrEqual(0);
    }
    expect(await page.getByTestId("company-documents").evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`documents-${size.width}.png`), animations: "disabled" });
  }
  await page.getByLabel("หมวดเอกสาร").selectOption("payable");
  await expect(page.locator("article[data-testid^='document-']")).toHaveCount(3);
  await page.getByRole("textbox", { name: "ค้นหาประเภทเอกสาร", exact: true }).fill("ไม่มีเอกสารนี้");
  await expect(page.getByRole("heading", { name: "ไม่พบประเภทเอกสาร" })).toBeVisible();
  expect(writes).toEqual([]);
});

test("purchase-only user cannot see accounting navigation", async ({ page }) => {
  await setup(page, ["inventory.purchase.view"]);
  await page.goto("/company/documents");
  await expect(page.locator("article[data-testid^='document-']")).toHaveCount(2);
  await expect(page.getByTestId("company-documents").locator('a[href^="/payable"], a[href="/etax"]')).toHaveCount(0);
  await expect(page.getByLabel("หมวดเอกสาร").locator('option[value="payable"]')).toHaveCount(0);
});

test("POS-only user is blocked when visiting documents directly", async ({ page }) => {
  await setup(page, ["pos.sale.create"]);
  await page.goto("/company/documents");
  await expect(page).toHaveURL(/\/403$/);
  await expect(page.getByTestId("company-documents")).toHaveCount(0);
});

test("context loading and server failure do not expose source actions", async ({ page }) => {
  await setup(page, DOCUMENT_CENTER_PERMISSIONS, { contextStatus: 503, delay: 700 });
  await page.goto("/company/documents");
  await expect(page.getByTestId("documents-loading")).toBeVisible();
  await expect(page.getByTestId("documents-loading")).toHaveCount(0);
  await expect(page.getByTestId("company-documents")).toHaveCount(0);
  await expect(page.locator("article[data-testid^='document-']")).toHaveCount(0);
});

test("mismatched company context blocks all document cards", async ({ page }) => {
  await setup(page, DOCUMENT_CENTER_PERMISSIONS, { mismatch: true });
  await page.goto("/company/documents");
  await expect(page.getByRole("heading", { name: "บริบทเอกสารไม่ตรงกับบัญชีที่ใช้งาน" })).toBeVisible();
  await expect(page.locator("article[data-testid^='document-']")).toHaveCount(0);
});

test("offline removes source links and reconnect restores them", async ({ page, context }) => {
  await setup(page);
  await page.goto("/company/documents");
  await expect(page.locator("article[data-testid^='document-'] a")).toHaveCount(11);
  await context.setOffline(true);
  await expect(page.getByTestId("documents-offline")).toBeVisible();
  await expect(page.locator("article[data-testid^='document-'] a")).toHaveCount(0);
  await context.setOffline(false);
  await expect(page.locator("article[data-testid^='document-'] a")).toHaveCount(11);
});

test("payable source tab follows the link and browser history", async ({ page }) => {
  await setup(page, ["accounting.payment.view"]);
  await page.goto("/company/documents");
  await page.getByRole("link", { name: "เปิดใบสำคัญจ่าย", exact: true }).click();
  await expect(page).toHaveURL(/\/payable\?tab=payments$/);
  await expect(page.getByRole("tab", { name: "บันทึกการจ่าย" })).toHaveAttribute("data-state", "active");
  await page.getByRole("tab", { name: "ใบรับรอง WHT" }).click();
  await expect(page).toHaveURL(/tab=wht$/);
  await page.goBack();
  await expect(page).toHaveURL(/tab=payments$/);
  await expect(page.getByRole("tab", { name: "บันทึกการจ่าย" })).toHaveAttribute("data-state", "active");
});

test("register searches and paginates without writes; offline hides source records", async ({ page, context }) => {
  const writes = await setup(page);
  await page.goto("/company/documents");
  const register = page.getByTestId("document-register");
  await expect(register.getByText("DOC-001", { exact: true })).toBeVisible();
  await register.getByRole("button", { name: "ถัดไป", exact: true }).click();
  await expect(register.getByText("DOC-002", { exact: true })).toBeVisible();
  await register.getByLabel("เลขเอกสาร", { exact: true }).fill("missing");
  await register.getByRole("button", { name: "ค้นหารายการ", exact: true }).click();
  await expect(register.getByText("ไม่พบรายการในสาขาและเงื่อนไขนี้")).toBeVisible();
  await register.getByLabel("เลขเอกสาร", { exact: true }).fill("");
  await register.getByRole("button", { name: "ค้นหารายการ", exact: true }).click();
  await expect(register.getByText("DOC-001", { exact: true })).toBeVisible();
  await context.setOffline(true);
  await expect(register.getByText("DOC-001", { exact: true })).toHaveCount(0);
  expect(writes).toEqual([]);
});

test("register context mismatch never displays returned records", async ({ page }) => {
  await setup(page, DOCUMENT_CENTER_PERMISSIONS, { registerMismatch: true });
  await page.goto("/company/documents");
  const register = page.getByTestId("document-register");
  await expect(register.getByRole("alert")).toContainText("บริบทเอกสารไม่ตรง");
  await expect(register.getByText("DOC-001", { exact: true })).toHaveCount(0);
});

test("register denied response is not presented as an empty success", async ({ page }) => {
  await setup(page, DOCUMENT_CENTER_PERMISSIONS, { registerStatus: 403 });
  await page.goto("/company/documents");
  const register = page.getByTestId("document-register");
  await expect(register.getByRole("alert")).toContainText("ไม่สามารถอ่านทะเบียน");
  await expect(register.getByText("ไม่พบรายการในสาขาและเงื่อนไขนี้")).toHaveCount(0);
});
