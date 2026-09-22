import { expect, test, type Route } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const tenantAccessToken = `header.${Buffer.from(JSON.stringify({ permissions: ["system.company.edit"], branch_id: null })).toString("base64url")}.signature`;

async function fulfill(route: Route, data: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ data, meta: { version: "test" }, error: null }),
  });
}

test("Company Admin sees shared raw stock and Brand-separated reporting in dark launch", async ({ page }) => {
  await page.addInitScript(({ company, token }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({
      state: {
        accessToken: token,
        refreshToken: "tenant-refresh-token",
        user: { id: "22222222-2222-4222-8222-222222222222", company_id: company, username: "owner", display_name: "Company Owner", is_active: true },
        companyId: company,
        businessSlug: "foodchainservice-test",
        branchId: null,
        stationKey: null,
        permissions: ["system.company.edit"],
      },
      version: 0,
    }));
  }, { company: companyId, token: tenantAccessToken });
  // Keep the test isolated from any locally running API. More specific routes
  // registered below take precedence over this safe empty fallback.
  await page.route("**/api/v1/**", (route) => fulfill(route, []));
  await page.route("**/api/v1/system/me/branches", (route) => fulfill(route, []));
  await page.route("**/api/v1/company-kitchen/dashboard", (route) => fulfill(route, {
    write_enabled: false,
    release: {
      release_stage: "read_only",
      writes_enabled: false,
      generated_at: new Date().toISOString(),
      stale_after_seconds: 300,
      hard_holds: ["opening_lot_physical_count", "quality_control_release", "recall_traceability"],
      checks: [
        { key: "company_context", label: "Company context", state: "pass", detail: "Signed scope" },
        { key: "opening_lot_physical_count", label: "Opening lot and physical count", state: "hold", detail: "Awaiting evidence" },
        { key: "quality_control_release", label: "QC hold and release", state: "hold", detail: "Not active" },
      ],
    },
    kitchen: { id: "k1", name: "ครัวกลาง Foodchainservice", branch_id: "c1", branch_name: "สาขาครัวกลาง", raw_location_id: "l1", raw_location_name: "คลัง RAW กลาง", timezone: "Asia/Bangkok", costing_method: "fifo", allow_negative_stock: false, is_active: true },
    ingredients: [{ id: "i1", code: "PORK", name: "หมู", canonical_product_id: "p1", base_unit_code: "g", unit_dimension: "mass", qty_on_hand: 1500, is_active: true }],
    aliases: [
      { id: "a1", ingredient_id: "i1", ingredient_name: "หมู", brand_id: "b1", brand_name: "หมูแดดเดียว", source_product_id: "pa", source_product_name: "หมูสูตร A", source_unit_code: "g", conversion_factor: 1, supplier_sku: null },
      { id: "a2", ingredient_id: "i1", ingredient_name: "หมู", brand_id: "b2", brand_name: "หมูหนักย่าง", source_product_id: "pb", source_product_name: "หมูสูตร B", source_unit_code: "g", conversion_factor: 1, supplier_sku: null },
    ],
    demands: [{ id: "d1", brand_id: "b1", brand_name: "หมูแดดเดียว", branch_id: "s1", branch_name: "ร้าน A", output_product_id: "oa", output_product_name: "หมูแดดเดียวพร้อมขาย", needed_on: "2026-09-15", requested_qty: 10, unit_code: "ea", status: "submitted", source_type: "store", source_id: "SO-A", note: null }],
    orders: [{ id: "o1", order_number: "CK-260915-TEST", brand_id: "b2", brand_name: "หมูหนักย่าง", output_product_id: "ob", output_product_name: "หมูหนักย่างพร้อมขาย", planned_date: "2026-09-15", status: "completed", planned_qty: 10, actual_output_qty: 10, waste_qty: 0, output_unit_code: "ea", total_input_cost: 100, output_cost_per_unit: 10, demand_id: null, recipe_id: "r2", note: null, inputs: [{ id: "in1", ingredient_id: "i1", ingredient_name: "หมู", planned_qty: 1000, actual_qty: 1000, base_unit_code: "g", actual_cost: 100 }] }],
    setup_options: {
      branches: [{ id: "c1", name: "สาขาครัวกลาง", code: "CK" }],
      locations: [{ id: "l1", branch_id: "c1", name: "คลัง RAW กลาง", code: "RAW" }],
      brands: [{ id: "b1", name: "หมูแดดเดียว", business_type: "restaurant" }, { id: "b2", name: "หมูหนักย่าง", business_type: "restaurant" }],
      brand_branches: [{ brand_id: "b1", branch_id: "c1" }, { brand_id: "b2", branch_id: "c1" }],
      products: [{ id: "p1", name: "หมู", sku: "PORK", brand_id: null, inventory_role: "central_raw", unit_code: "g" }],
    },
  }));
  await page.route("**/api/v1/company-kitchen/report**", (route) => fulfill(route, {
    date_from: "2026-09-08",
    date_to: "2026-09-14",
    production_by_brand: [
      { brand_id: "b1", brand_name: "หมูแดดเดียว", order_count: 1, completed_count: 1, output_qty: 10, waste_qty: 0, input_cost: 100 },
      { brand_id: "b2", brand_name: "หมูหนักย่าง", order_count: 1, completed_count: 1, output_qty: 10, waste_qty: 1, input_cost: 110 },
    ],
    ingredient_usage: [
      { brand_id: "b1", brand_name: "หมูแดดเดียว", ingredient_id: "i1", ingredient_name: "หมู", consumed_qty: 1000, reversed_qty: 0, net_cost: 100, unit_code: "g" },
      { brand_id: "b2", brand_name: "หมูหนักย่าง", ingredient_id: "i1", ingredient_name: "หมู", consumed_qty: 1000, reversed_qty: 0, net_cost: 110, unit_code: "g" },
    ],
    orders: [],
  }));

  await page.goto("/company-kitchen");
  await expect(page.getByRole("heading", { name: "ครัวกลางและวัตถุดิบร่วม" })).toBeVisible();
  await expect(page.getByTestId("company-kitchen-dark-launch")).toBeVisible();
  await expect(page.getByText("Read-only Dark Launch · ครัวกลาง")).toBeVisible();
  await expect(page.locator('[data-release-check="opening_lot_physical_count"]')).toBeVisible();
  await expect(page.getByText("หมู", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("1,500 g")).toBeVisible();
  await page.getByRole("tab", { name: "ตั้งค่าและ Mapping" }).click();
  await expect(page.getByText("หมูแดดเดียว: หมูสูตร A")).toBeVisible();
  await expect(page.getByText("หมูหนักย่าง: หมูสูตร B")).toBeVisible();
  await expect(page.getByRole("button", { name: "บันทึก", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "บันทึก Mapping" })).toBeDisabled();
  await page.getByRole("tab", { name: "รายงาน" }).click();
  await expect(page.getByText("การใช้วัตถุดิบแยกแบรนด์")).toBeVisible();
  await expect(page.getByText("฿100.00").first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
