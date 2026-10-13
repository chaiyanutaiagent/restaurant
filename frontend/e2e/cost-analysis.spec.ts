import { expect, test, type Page } from "@playwright/test";
const companyId="11111111-1111-4111-8111-111111111111", branchId="22222222-2222-4222-8222-222222222222";
async function setup(page: Page, mode="normal"): Promise<string[]> {
  const writes: string[]=[];
  await page.addInitScript(({companyId,branchId})=>localStorage.setItem("erp-auth",JSON.stringify({state:{
    accessToken:"local-test",refreshToken:"refresh",user:{id:"tester",username:"cost.tester",company_id:companyId,display_name:"Tester",is_active:true},
    companyId,branchId,permissions:["accounting.report.view"],scopeTypes:["company","branch"],businessType:"restaurant",targetDatabase:"restaurant",stationKey:null},version:0})),{companyId,branchId});
  await page.route("**/api/v1/**",async route=>{
    const req=route.request(), url=new URL(req.url()), path=url.pathname;
    if(req.method()!=="GET") writes.push(path);
    let data: unknown=[];
    if(path.endsWith("/company/context")) data={contract_version:"2026-09-19.1",environment:"uat",
      company:{id:companyId,name:"บริษัททดสอบต้นทุน"},branch:{id:branchId,code:"BKK-01",name:"สาขาทดสอบ"},brand:null,
      business_type:"restaurant",target_database:"restaurant",currency:"THB",timezone:"Asia/Bangkok",tax:{},
      all_scope_allowed:{brand:true,branch:true,station:false},updated_at:new Date().toISOString()};
    else if(path.endsWith("/company/action-center")) data={items:[],total:0,unread:0};
    else if(path.endsWith("/company/cost-analysis")) {
      if(mode==="error") return route.fulfill({status:403,json:{detail:"Denied"}});
      const p=url.searchParams, f=Number(p.get("fixed_cost")),v=Number(p.get("variable_pct")),s=Number(p.get("target_sales"));
      data={company_id:mode==="mismatch"?"wrong":companyId,branch_id:branchId,start:p.get("start"),end:p.get("end"),
        generated_at:mode==="stale"?"2020-01-01T00:00:00Z":new Date().toISOString(),posting_lines:mode==="empty"?0:5,
        summary:{revenue:900,cogs:400,other_expense:100,gross_profit:500,posted_result:400,gross_margin_pct:55.56},
        accounts:mode==="empty"?[]:[{id:"a",code:"4100",name:"รายได้ทดสอบ",group:"revenue",debit:100,credit:1000,amount:900}],
        scenario:{fixed_cost:f,variable_pct:v,target_sales:s,break_even_sales:v===100?null:f/(1-v/100),projected_result:s*(1-v/100)-f,margin_of_safety:v===100?null:s-f/(1-v/100)}};
    }
    return route.fulfill({json:{data,error:null}});
  });
  return writes;
}
test("tablet actual ledger, explicit scenario and offline are read-only",async({page,context},info)=>{
  const writes=await setup(page);
  await page.setViewportSize({width:820,height:1180}); await page.goto("/company/cost-analysis");
  await expect(page.getByText("4100 · รายได้ทดสอบ")).toBeVisible();
  await expect(page.getByTestId("simulation")).toHaveCount(0);
  await page.getByLabel("ต้นทุนคงที่",{exact:true}).fill("30000");
  await page.getByLabel("อัตราต้นทุนผันแปร").fill("60"); await page.getByLabel("ยอดขายเป้าหมาย",{exact:true}).fill("100000");
  await page.getByRole("button",{name:"คำนวณสมมติฐาน",exact:true}).click();
  await expect(page.getByTestId("simulation")).toContainText("75,000.00");
  expect(await page.getByTestId("cost-analysis").evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.screenshot({path:info.outputPath("cost-tablet.png"),fullPage:true});
  await page.getByLabel("อัตราต้นทุนผันแปร").fill("100"); await page.getByRole("button",{name:"คำนวณสมมติฐาน",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("ไม่มีกำไรส่วนเกิน");
  await context.setOffline(true); await expect(page.getByRole("status")).toContainText("ออฟไลน์");
  await expect(page.getByRole("region",{name:"ผลจากบัญชี"})).toHaveCount(0); expect(writes).toEqual([]);
});
for(const mode of ["mismatch","error","stale","empty"]) test(`cost ${mode} state`,async({page})=>{
  await setup(page,mode); await page.goto("/company/cost-analysis");
  await expect(page.getByTestId("cost-analysis")).toContainText(mode==="mismatch"?"บริบทไม่ตรง":mode==="error"?"อ่านรายงานไม่ได้":mode==="stale"?"ข้อมูลเกิน 5 นาที":"ไม่พบรายการรายได้หรือต้นทุน");
  if(mode!=="empty") await expect(page.getByRole("region",{name:"ผลจากบัญชี"})).toHaveCount(0);
});
