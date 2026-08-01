import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";

type BrowserContextRecord = {
  company_id: string;
  brand_slug: string;
  browser_table_name: string;
  browser_session_id: string;
  browser_qr_token: string;
  browser_paths: {
    public_menu: string;
    tables: string;
    kitchen: string;
    report: string;
  };
};

const contextPath = process.env.P5_BROWSER_CONTEXT_FILE;
const adminPassword = process.env.P5_UAT_ADMIN_PASSWORD;
const artifactDir = process.env.P5_READINESS_ARTIFACT_DIR ?? "/private/tmp/restaurant-p5-playwright";

if (!contextPath || !adminPassword) {
  throw new Error("P5_BROWSER_CONTEXT_FILE and P5_UAT_ADMIN_PASSWORD are required");
}

const uat = JSON.parse(readFileSync(contextPath, "utf8")) as BrowserContextRecord;
mkdirSync(artifactDir, { recursive: true });

function watchPage(page: Page, failures: string[]): void {
  page.on("pageerror", (error) => failures.push(`pageerror ${page.url()}: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") failures.push(`console ${page.url()}: ${message.text()}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 500) failures.push(`HTTP ${response.status()} ${response.url()}`);
  });
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
}

async function loginStaff(page: Page): Promise<void> {
  await page.goto(`/login?next=${encodeURIComponent(uat.browser_paths.tables)}`);
  await page.locator("#company_id").fill(uat.company_id);
  await page.locator("#username").fill("admin");
  await page.locator("#password").fill(adminPassword as string);
  await page.getByRole("button", { name: "เข้าสู่ระบบ" }).click();
  await expect(page).toHaveURL(new RegExp(`${uat.browser_paths.tables.replaceAll("/", "\\/")}$`));
}

test("mobile QR to tablet kitchen, checkout, and ERP report", async ({ browser, baseURL }) => {
  const failures: string[] = [];
  const mobileContext: BrowserContext = await browser.newContext({
    baseURL,
    viewport: { width: 360, height: 800 },
    deviceScaleFactor: 2,
    hasTouch: true,
    isMobile: true,
    locale: "th-TH",
  });
  const staffContext: BrowserContext = await browser.newContext({
    baseURL,
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 1,
    hasTouch: true,
    locale: "th-TH",
  });
  const customer = await mobileContext.newPage();
  const staff = await staffContext.newPage();
  watchPage(customer, failures);
  watchPage(staff, failures);

  try {
    await customer.goto(uat.browser_paths.public_menu);
    await expect(customer.getByText(`โต๊ะ ${uat.browser_table_name}`)).toBeVisible();
    await expect(customer.getByText("Browser UAT หวานน้อย")).toBeVisible();
    await expect(customer.getByText("สถานะออเดอร์")).toBeVisible();
    await assertNoHorizontalOverflow(customer);
    await customer.screenshot({ path: `${artifactDir}/01-mobile-public-menu.png`, fullPage: true });

    await loginStaff(staff);
    await expect(staff.getByText(uat.browser_table_name)).toBeVisible();
    await staff.screenshot({ path: `${artifactDir}/02-table-session-state.png`, fullPage: true });

    await staff.goto(uat.browser_paths.kitchen);
    await expect(staff.getByRole("heading", { name: "Kitchen Display" })).toBeVisible();
    await expect(staff.getByText("Browser UAT หวานน้อย")).toBeVisible();
    await assertNoHorizontalOverflow(staff);
    await staff.screenshot({ path: `${artifactDir}/03-kitchen-pending.png`, fullPage: true });

    for (const action of ["เริ่มทำ", "เสร็จแล้ว"]) {
      const button = staff.getByRole("button", { name: action }).first();
      await expect(button).toBeVisible();
      await button.click();
    }

    await expect(staff.getByText("เสร็จแล้ว", { exact: true }).first()).toBeVisible();
    await staff.goto(`/restaurant/session/${uat.browser_session_id}/detail`);
    const servedButton = staff.getByRole("button", { name: "เสิร์ฟแล้ว" }).first();
    await expect(servedButton).toBeVisible();
    await servedButton.click();
    await expect(servedButton).not.toBeVisible();

    await customer.reload();
    await expect(customer.getByText("อาหารพร้อมเสิร์ฟแล้ว")).toBeVisible();
    await customer.getByRole("button", { name: "เรียกบิล" }).click();
    await expect(customer.getByText("เรียกบิลแล้ว")).toBeVisible();
    await customer.screenshot({ path: `${artifactDir}/04-mobile-bill-requested.png`, fullPage: true });

    await staff.goto(`/restaurant/session/${uat.browser_session_id}/checkout`);
    await expect(staff.getByRole("heading", { name: new RegExp(`รวมบิล.*${uat.browser_table_name}`) })).toBeVisible();
    await staff.locator('input[type="number"]').nth(1).fill("10000");
    await staff.getByRole("button", { name: /^ชำระเงิน/ }).click();
    await expect(staff.getByRole("heading", { name: "ชำระเงินสำเร็จ" })).toBeVisible();
    await staff.screenshot({ path: `${artifactDir}/05-checkout-success.png`, fullPage: true });

    await staff.goto(uat.browser_paths.report);
    await expect(staff.getByRole("heading", { name: "รายงานส่วนกลาง" })).toBeVisible();
    await expect(staff.getByRole("heading", { name: "ตรวจยอดรายการต้นทาง" })).toBeVisible();
    await expect(staff.getByText(/ผลต่างรายสาขา/)).toBeVisible();
    await staff.screenshot({ path: `${artifactDir}/06-erp-reconciliation.png`, fullPage: true });

    expect(failures, failures.join("\n")).toEqual([]);
  } finally {
    await mobileContext.close();
    await staffContext.close();
  }
});
