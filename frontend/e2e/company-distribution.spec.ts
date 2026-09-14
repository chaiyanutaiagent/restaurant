import { expect, test, type Route } from "@playwright/test";

const companyId = "11111111-1111-4111-8111-111111111111";
const token = `header.${Buffer.from(JSON.stringify({ permissions: ["system.company.edit"], branch_id: null })).toString("base64url")}.signature`;

async function fulfill(route: Route, data: unknown): Promise<void> {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ data, meta: { version: "test" }, error: null }) });
}

test("Company Admin tracks demand and finished-goods reconciliation in dark launch", async ({ page }) => {
  await page.addInitScript(({ company, accessToken }) => {
    window.localStorage.setItem("erp-auth", JSON.stringify({ state: {
      accessToken, refreshToken: "refresh", user: { id: "22222222-2222-4222-8222-222222222222", company_id: company, username: "owner", display_name: "Company Owner", is_active: true },
      companyId: company, businessSlug: "foodchainservice-test", branchId: null, stationKey: null, permissions: ["system.company.edit"],
    }, version: 0 }));
  }, { company: companyId, accessToken: token });
  await page.route("**/api/v1/**", (route) => fulfill(route, []));
  await page.route("**/api/v1/system/me/branches", (route) => fulfill(route, []));
  await page.route("**/api/v1/company-distribution/dashboard", (route) => fulfill(route, {
    write_enabled: false,
    demands: [
      { id: "d1", source_module: "restaurant_pos", brand_id: "b1", brand_name: "หมูแดดเดียว", branch_id: "s1", branch_name: "สาขาสยาม", product_id: "p1", product_name: "หมูแดดเดียวพร้อมขาย", needed_on: "2026-09-15", requested_qty: 10, allocated_qty: 10, net_received_qty: 8, unit_code: "ea", status: "allocated", source_type: "restaurant_replenishment", source_id: "REQ-001", note: null },
      { id: "d2", source_module: "takeaway_pos", brand_id: "b2", brand_name: "Takeaway Express", branch_id: "s2", branch_name: "จุดขาย A", product_id: "p2", product_name: "ชุดพร้อมขาย", needed_on: "2026-09-15", requested_qty: 5, allocated_qty: 5, net_received_qty: 0, unit_code: "ea", status: "allocated", source_type: "takeaway_replenishment", source_id: "REQ-002", note: null },
    ],
    shipments: [
      { id: "sh1", shipment_number: "DS20260914-0001", demand_id: "d1", transfer_order_id: "to1", transfer_number: "TO20260914-0001", source_module: "restaurant_pos", brand_id: "b1", brand_name: "หมูแดดเดียว", branch_id: "s1", branch_name: "สาขาสยาม", product_id: "p1", product_name: "หมูแดดเดียวพร้อมขาย", status: "rejected", planned_qty: 10, shipped_qty: 10, received_qty: 8, rejected_qty: 2, returned_qty: 0, in_transit_qty: 0, net_received_qty: 8, unit_code: "ea", unit_cost: 20, dispatched_at: "2026-09-14T03:00:00Z", settled_at: "2026-09-14T04:00:00Z", note: null, events: [] },
    ],
    setup_options: { brands: [{ id: "b1", name: "หมูแดดเดียว", business_type: "restaurant", source_module: "restaurant_pos" }], brand_branches: [{ brand_id: "b1", branch_id: "s1", branch_name: "สาขาสยาม", store_location_id: "l2" }], products: [{ id: "p1", brand_id: "b1", name: "หมูแดดเดียวพร้อมขาย", sku: "PORK-READY", unit_code: "ea", available_qty: 20 }] },
  }));
  await page.route("**/api/v1/company-distribution/report**", (route) => fulfill(route, {
    date_from: "2026-09-08", date_to: "2026-09-14",
    totals: { planned_qty: 10, shipped_qty: 10, received_qty: 8, rejected_qty: 2, returned_qty: 0, in_transit_qty: 0, net_received_qty: 8 },
    by_workspace: [{ source_module: "restaurant_pos", brand_id: "b1", brand_name: "หมูแดดเดียว", branch_id: "s1", branch_name: "สาขาสยาม", shipment_count: 1, planned_qty: 10, shipped_qty: 10, received_qty: 8, rejected_qty: 2, returned_qty: 0, in_transit_qty: 0, net_received_qty: 8 }],
    shipments: [],
  }));

  await page.goto("/company-distribution");
  await expect(page.getByRole("heading", { name: "Demand และกระจายสินค้าสำเร็จรูป" })).toBeVisible();
  await expect(page.getByTestId("company-distribution-dark-launch")).toBeVisible();
  await expect(page.getByText("Restaurant POS").first()).toBeVisible();
  await expect(page.getByText("Takeaway POS").first()).toBeVisible();
  await page.getByRole("tab", { name: "Demand", exact: true }).click();
  await expect(page.getByRole("button", { name: "ส่ง Demand" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "สร้าง Shipment" })).toBeDisabled();
  await page.getByRole("tab", { name: "ส่ง–รับ–คืน" }).click();
  await expect(page.getByText("DS20260914-0001")).toBeVisible();
  await page.getByRole("tab", { name: "Reconciliation" }).click();
  await expect(page.getByText("ตรวจยอดแยกตามระบบ / แบรนด์ / สาขา")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
