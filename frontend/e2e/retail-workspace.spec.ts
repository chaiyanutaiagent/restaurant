import { expect, test, type Page, type Route } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const brandId = "22222222-2222-4222-8222-222222222222";
const branchId = "33333333-3333-4333-8333-333333333333";
const userId = "55555555-5555-4555-8555-555555555555";
const locationId = "66666666-6666-4666-8666-666666666666";
const shiftId = "77777777-7777-4777-8777-777777777777";
const permissions = [
  "pos.sale.view",
  "pos.sale.create",
  "pos.draft.view",
  "pos.draft.create",
  "pos.refund.view",
  "system.device.view",
];

function response(data: unknown, meta: Record<string, unknown> = {}): string {
  return JSON.stringify({ data, meta: { version: "test", ...meta }, error: null });
}

async function fulfill(route: Route, data: unknown, meta: Record<string, unknown> = {}, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", body: response(data, meta) });
}

async function installRetailSession(page: Page): Promise<void> {
  const payload = {
    permissions,
    scope_types: ["company", "branch"],
    company_id: companyId,
    branch_id: branchId,
    brand_id: brandId,
    business_type: "retail_pos",
    target_database: "retail_pos",
  };
  const token = `header.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.signature`;
  await page.addInitScript(({ accessToken, catalogKey, company, brand, branch, user, userPermissions }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({ state: {
      accessToken,
      refreshToken: "test-refresh",
      companyId: company,
      branchId: branch,
      brandId: brand,
      businessSlug: "foodchain-retail-uat",
      businessType: "retail_pos",
      targetDatabase: "retail_pos",
      scopeTypes: ["company", "branch"],
      stationKey: null,
      permissions: userPermissions,
      user: {
        id: user,
        company_id: company,
        username: "retail-cashier",
        email: "retail@example.com",
        phone: null,
        first_name: null,
        last_name: null,
        display_name: "Retail Cashier",
        is_active: true,
        is_superuser: false,
        last_login_at: null,
      },
    }, version: 0 }));
    window.localStorage.setItem("pos-catalog-isolation-key", catalogKey);
  }, {
    accessToken: token,
    catalogKey: `${companyId}:${brandId}:${branchId}:retail_pos:retail_sale`,
    company: companyId,
    brand: brandId,
    branch: branchId,
    user: userId,
    userPermissions: permissions,
  });
}

async function mockRetailApis(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/my-branches")) {
      return fulfill(route, [{ id: branchId, code: "BKK", name: "Retail UAT", brand_id: brandId }]);
    }
    if (path.endsWith("/stock/locations")) {
      return fulfill(route, [{ id: locationId, company_id: companyId, branch_id: branchId, code: "SHOP", name: "หน้าร้าน", description: null, is_active: true }]);
    }
    if (path.endsWith("/pos/shifts/current")) {
      return fulfill(route, {
        id: shiftId,
        shift_number: "RS20260923-001",
        shift_type: "staff_cashier",
        version: 1,
        status: "open",
        branch_id: branchId,
        location_id: locationId,
        user_id: userId,
        opened_at: "2026-09-23T08:00:00Z",
        closed_at: null,
        opening_cash: 1000,
        closing_cash: null,
        expected_cash: null,
        cash_difference: null,
        total_sales: 0,
        total_orders: 0,
        total_voids: 0,
        close_reason_code: null,
        cash_count_json: null,
        opened_device_id: null,
        opened_device_code: null,
        closed_device_id: null,
        closed_device_code: null,
        closed_by_user_id: null,
        close_snapshot_json: null,
      });
    }
    if (path.includes(`/system/branches/${branchId}/settings`)) {
      return fulfill(route, {
        id: "88888888-8888-4888-8888-888888888888",
        branch_id: branchId,
        pos_require_customer: false,
        pos_allow_discount: true,
        pos_max_discount_pct: 20,
        pos_cashier_discount_limit_pct: 10,
        pos_price_override_auto_limit_pct: 0,
        pos_price_override_auto_limit_amount: 0,
        pos_price_override_max_deviation_pct: 0,
        pos_price_override_min_margin_pct: 0,
        pos_price_override_self_approval: false,
        pos_hold_draft_ttl_minutes: 120,
        receipt_copies: 1,
        allow_negative_stock: false,
      });
    }
    if (path.endsWith("/products/retail/lookup")) {
      return fulfill(route, { status: "not_found", product: null, stock: null, reason_code: "not_found" });
    }
    if (path.endsWith("/products")) return fulfill(route, [], { total: 0, page: 1, limit: 100 });
    if (path.endsWith("/categories") || path.endsWith("/units") || path.endsWith("/stock/balances") || path.endsWith("/pos/drafts") || path.endsWith("/pos/sales") || path.endsWith("/system/branches/replacement-rules")) {
      return fulfill(route, []);
    }
    if (path.endsWith("/crm/settings")) return fulfill(route, {});
    return fulfill(route, []);
  });
}

test.beforeEach(async ({ page }) => {
  await installRetailSession(page);
  await mockRetailApis(page);
});

test("Retail workspace stays server-authoritative and usable on desktop and tablet", async ({ page }) => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 820, height: 1180 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/retail/pos");
    await expect(page.getByText("Retail POS", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Pilot · Production ใช้ Legacy/)).toBeVisible();
    await expect(page.getByText(/Retail Scan-first · Pilot/)).toBeVisible();
    await expect(page.getByText(/signed Company \/ Brand \/ Branch/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  }

  const lookup = page.waitForRequest((request) => request.url().includes("/api/v1/products/retail/lookup"));
  const search = page.getByPlaceholder("สแกนบาร์โค้ด / ค้นหาชื่อ / SKU");
  await search.fill("8850000000001");
  await search.press("Enter");
  const lookupRequest = await lookup;
  expect(new URL(lookupRequest.url()).searchParams.get("location_id")).toBe(locationId);
  await expect(page.getByText("ไม่พบบาร์โค้ด", { exact: true })).toBeVisible();
});

async function mobileCatalog(page: Page) {
  const id = "99999999-9999-4999-8999-999999999999";
  const product = {id,company_id:companyId,brand_id:brandId,name:"น้ำดื่มทดสอบมือถือ",sku:"MOBILE-WATER",barcode:"8850000000001",product_type:"simple",inventory_role:"store_local",selling_price:10,cost_price:5,vat_type:"included",vat_rate:7,is_active:true,is_for_sale:true,is_for_purchase:true,unit:{code:"PCS",name:"ขวด"},category_id:null,created_at:"2026-10-13T00:00:00Z"};
  await page.route("**/api/v1/products?**",route=>fulfill(route,[product],{total:1,page:1,limit:100}));
  await page.route("**/api/v1/stock/balances?**",route=>fulfill(route,[{id:locationId,product_id:id,branch_id:branchId,location_id:locationId,variant_id:null,qty_on_hand:20,qty_available:20,min_stock_qty:0}]));
  await page.route("**/api/v1/products/retail/lookup?**",route=>fulfill(route,{result:"matched",code:product.barcode,product:{...product,server_price:10,available_qty:20,selected_variant_id:null,variants:[]},validation_time:new Date().toISOString(),error_code:null}));
  let price = 10;
  await page.route("**/api/v1/pos/pricing/calculate",route=>{
    const payload=route.request().postDataJSON();
    const qty=payload.items[0].qty;
    return fulfill(route,{quote_id:"quote-mobile",total_amount:price*qty,discount_percentage:0,has_price_discrepancy:price!==10,lines:[{product_id:id,variant_id:null,authoritative_unit_price:price,price_version:"v1",discrepancy:price!==10}]});
  });
  const sales:unknown[]=[];
  await page.route("**/api/v1/pos/sales",async route=>{
    if(route.request().method()!=="POST")return route.fallback();
    sales.push(route.request().postDataJSON());
    await route.fulfill({status:409,contentType:"application/json",body:JSON.stringify({detail:"จำลองปฏิเสธการขาย"})});
  });
  return {sales,setPrice:(next:number)=>{price=next;}};
}

test("Retail phone flow retains cart, validates payment, blocks offline and surfaces server price changes",async({page,context})=>{
  const mock=await mobileCatalog(page);
  await page.setViewportSize({width:390,height:844});
  await page.goto("/retail/pos");
  const footer=page.getByTestId("retail-mobile-footer");
  await expect(footer).toBeVisible();
  await expect(page.getByTestId("pos-cart-panel")).toBeHidden();
  await expect(page.getByTestId("retail-pos-workspace-bar")).toBeHidden();
  await page.getByRole("button",{name:"เมนูเพิ่มเติม",exact:true}).click();
  await expect(page.getByTestId("retail-pos-workspace-bar")).toBeVisible();
  await page.getByRole("button",{name:"ปิดเมนู",exact:true}).click();
  await page.getByTestId("pos-product-panel").getByRole("button",{name:/น้ำดื่มทดสอบมือถือ/}).click();
  await expect(footer).toContainText("ดูตะกร้า (1)");
  await footer.getByRole("button").click();
  await expect(page.getByRole("heading",{name:"ตรวจตะกร้า"})).toBeFocused();
  await expect(page.getByTestId("pos-product-panel")).toBeHidden();
  await expect(page.getByTestId("pos-checkout-panel")).toBeHidden();
  await page.getByRole("button",{name:"เพิ่มจำนวน น้ำดื่มทดสอบมือถือ",exact:true}).click();
  await expect(footer).toContainText("20.00");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:"/private/tmp/restaurant-retail-mobile-cart.png",fullPage:true});
  await page.getByRole("button",{name:"เลือกสินค้าเพิ่ม",exact:true}).click();
  await expect(footer).toContainText("ดูตะกร้า (2)");
  await footer.getByRole("button").click();
  await footer.getByRole("button").click();
  await expect(page.getByRole("heading",{name:"รับชำระเงิน"})).toBeVisible();
  await expect(page.getByTestId("pos-cart-body")).toBeHidden();
  const confirm=page.getByRole("button",{name:/ยืนยันรับเงิน/});
  await expect(confirm).toBeDisabled();
  await page.getByLabel("จำนวนเงินที่รับ",{exact:true}).fill("100");
  await expect(page.getByText("เงินทอน: ฿80.00",{exact:true})).toBeVisible();
  await expect(confirm).toBeEnabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:"/private/tmp/restaurant-retail-mobile-payment.png",fullPage:true});
  await context.setOffline(true);
  await expect(confirm).toBeDisabled();
  await context.setOffline(false);
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByText("ชำระเงินไม่สำเร็จ",{exact:true})).toBeVisible();
  expect(mock.sales).toHaveLength(1);
  expect(mock.sales[0]).toMatchObject({payment_method:"cash",items:[{qty:2,unit_price:10}]});
  await expect(page.getByLabel("จำนวนเงินที่รับ",{exact:true})).toHaveValue("100");
  mock.setPrice(12);
  await confirm.click();
  await expect(page.getByText("ราคามีการเปลี่ยนแปลง",{exact:true})).toBeVisible();
  await expect(page.getByTestId("pos-product-panel")).toBeVisible();
  expect(mock.sales).toHaveLength(1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test("Retail small phone and tablet resize preserves cart and both desktop panels",async({page})=>{
  await mobileCatalog(page);
  await page.setViewportSize({width:320,height:740});
  await page.goto("/retail/pos");
  await page.getByTestId("pos-product-panel").getByRole("button",{name:/น้ำดื่มทดสอบมือถือ/}).click();
  const footer=page.getByTestId("retail-mobile-footer");
  await expect(footer).toContainText("ดูตะกร้า (1)");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  await page.screenshot({path:"/private/tmp/restaurant-retail-mobile-catalog.png",fullPage:true});
  await footer.getByRole("button").click();
  await page.setViewportSize({width:820,height:1180});
  await expect(footer).toBeHidden();
  await expect(page.getByTestId("pos-product-panel")).toBeVisible();
  await expect(page.getByTestId("pos-cart-body")).toBeVisible();
  await expect(page.getByTestId("pos-checkout-panel")).toBeVisible();
  await page.setViewportSize({width:320,height:740});
  await expect(page.getByLabel("จำนวน น้ำดื่มทดสอบมือถือ",{exact:true})).toHaveValue("1");
  await page.getByRole("button",{name:"นำ น้ำดื่มทดสอบมือถือ ออกจากตะกร้า",exact:true}).click();
  await expect(footer.getByRole("button")).toBeDisabled();
});
