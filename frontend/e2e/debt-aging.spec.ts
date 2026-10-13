import { expect, test, type Page } from "@playwright/test";
const companyId="11111111-1111-4111-8111-111111111111", branchId="22222222-2222-4222-8222-222222222222";
async function setup(page: Page, mode="normal"): Promise<{ writes: string[]; queries: string[] }> {
  const writes: string[]=[], queries: string[]=[];
  await page.addInitScript(({companyId,branchId})=>localStorage.setItem("erp-auth",JSON.stringify({state:{
    accessToken:"local-test",refreshToken:"refresh",user:{id:"tester",username:"aging.tester",company_id:companyId,display_name:"Tester",is_active:true},
    companyId,branchId,permissions:["accounting.report.view","accounting.payment.view"],scopeTypes:["company","branch"],
    businessType:"restaurant",targetDatabase:"restaurant",stationKey:null},version:0})),{companyId,branchId});
  await page.route("**/api/v1/**",async route=>{
    const req=route.request(), url=new URL(req.url()), path=url.pathname;
    if(req.method()!=="GET") writes.push(path);
    let data: unknown=[];
    if(path.endsWith("/company/context")) data={contract_version:"2026-09-19.1",environment:"uat",
      company:{id:companyId,name:"บริษัททดสอบอายุหนี้"},branch:{id:branchId,code:"BKK-01",name:"สาขาทดสอบ"},brand:null,
      business_type:"restaurant",target_database:"restaurant",currency:"THB",timezone:"Asia/Bangkok",tax:{},
      all_scope_allowed:{brand:true,branch:true,station:false},updated_at:new Date().toISOString()};
    else if(path.endsWith("/company/action-center")) data={items:[],total:0,unread:0};
    else if(path.endsWith("/company/debt-aging")) {
      queries.push(url.search);
      if(mode==="error") return route.fulfill({status:403,json:{detail:"Denied"}});
      const empty=url.searchParams.get("search")==="missing";
      data={company_id:mode==="mismatch"?"wrong":companyId,branch_id:branchId,side:"payable",generated_at:mode==="stale"?"2020-01-01T00:00:00Z":new Date().toISOString(),aging_date:"2026-10-13",
        summary:{count:empty?0:26,outstanding:2600,overdue:2000,due_today:100,next7:300,next30:600,
          bucket_not_due:500,bucket_due_today:100,bucket_days_1_30:500,bucket_days_31_60:500,bucket_days_61_90:500,bucket_days_91_plus:500,warnings:0},
        items:empty?[]:[{id:"source-1",document_id:"doc-1",number:"AP-001",partner_name:"คู่ค้าทดสอบ",due_date:"2026-10-01",total_amount:150,paid_amount:50,outstanding:100,days_overdue:12,bucket:"days_1_30",balance_warning:false}],
        partners:[],has_more:url.searchParams.get("page")==="1",document_kind:"supplier_invoice"};
    }
    return route.fulfill({json:{data,error:null}});
  });
  return {writes,queries};
}
test("aging tablet filters, paging, empty, read-only and offline",async({page,context},info)=>{
  const {writes,queries}=await setup(page);
  await page.setViewportSize({width:820,height:1180}); await page.goto("/company/debt-aging");
  await expect(page.getByRole("button",{name:"AP-001"})).toBeVisible();
  await expect(page.getByLabel("ประเภทหนี้").locator("option")).toHaveCount(1);
  await page.getByLabel("กำหนดชำระ",{exact:true}).selectOption("next7");
  await expect.poll(()=>queries.at(-1)).toContain("window=next7");
  await page.getByRole("button",{name:"ถัดไป",exact:true}).click();
  await expect.poll(()=>queries.at(-1)).toContain("page=2");
  expect(await page.getByTestId("debt-aging").evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.screenshot({path:info.outputPath("aging-tablet.png"),animations:"disabled"});
  await page.getByLabel("ค้นหาคู่ค้าหรือเลขเอกสาร").fill("missing"); await page.getByRole("button",{name:"ค้นหา",exact:true}).click();
  await expect(page.getByText("ไม่พบหนี้ค้างตามตัวกรองนี้")).toBeVisible();
  await context.setOffline(true); await expect(page.getByRole("status")).toContainText("ออฟไลน์");
  await expect(page.getByRole("region",{name:"ยอดสรุป"})).toHaveCount(0);
  expect(writes).toEqual([]);
});
for(const mode of ["mismatch","error","stale"]) test(`aging ${mode} hides financial data`,async({page})=>{
  await setup(page,mode); await page.goto("/company/debt-aging");
  await expect(page.getByTestId("debt-aging")).toContainText(mode==="mismatch"?"บริบทไม่ตรง":mode==="error"?"อ่านรายงานไม่ได้":"ข้อมูลเกิน 5 นาที");
  await expect(page.getByRole("button",{name:"AP-001"})).toHaveCount(0);
  await expect(page.getByRole("region",{name:"ยอดสรุป"})).toHaveCount(0);
});
