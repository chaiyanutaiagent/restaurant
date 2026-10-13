import { expect, test, type Page } from "@playwright/test";
const companyId="11111111-1111-4111-8111-111111111111",brandId="22222222-2222-4222-8222-222222222222",branchId="33333333-3333-4333-8333-333333333333";
const output="44444444-4444-4444-8444-444444444444",ingredient="55555555-5555-4555-8555-555555555555";
async function setup(page:Page,mode="normal"):Promise<string[]> {
  const writes:string[]=[];
  let rows:Record<string,unknown>[]=[];
  await page.addInitScript(({companyId,brandId,branchId})=>localStorage.setItem("erp-auth",JSON.stringify({state:{accessToken:"test",refreshToken:"test",user:{id:"author",username:"recipe.author",company_id:companyId,display_name:"ผู้เสนอ",is_active:true},companyId,brandId,branchId,permissions:["fb.recipe.manage"],scopeTypes:["branch"],businessType:"restaurant",targetDatabase:"restaurant",stationKey:null},version:0})),{companyId,brandId,branchId});
  await page.route("**/api/v1/**",async route=>{
    const req=route.request(),p=new URL(req.url()).pathname;
    let data:unknown=[];
    if(req.method()!=="GET") writes.push(p);
    if(p.endsWith("/company/context")) data={contract_version:"2026-09-19.1",environment:"uat",company:{id:companyId,name:"บริษัททดสอบสูตร"},brand:{id:brandId,name:"ร้านทดสอบ"},branch:{id:branchId,name:"สาขาทดสอบ",code:"BKK-01"},business_type:"restaurant",target_database:"restaurant",currency:"THB",timezone:"Asia/Bangkok",tax:{},all_scope_allowed:{brand:false,branch:false,station:false},updated_at:new Date().toISOString()};
    else if(p.endsWith("/company/action-center")) data={items:[],total:0,unread:0};
    else if(p.endsWith("/recipe-reviews/options")) {
      if(mode==="error") return route.fulfill({status:403,json:{detail:"Denied"}});
      data={company_id:mode==="mismatch"?"other":companyId,manager:false,brands:[{id:brandId,name:"ร้านทดสอบ",system:"restaurant"}],branches:[{id:branchId,brand_id:brandId,name:"สาขาทดสอบ",code:"BKK-01"}]};
    } else if(p.endsWith("/recipe-reviews/catalog")) data=[{id:output,name:"หมูย่าง",sku:"FG",unit:"kg"},{id:ingredient,name:"หมูดิบ",sku:"RAW",unit:"kg"}];
    else if(p.endsWith("/recipe-reviews/sources")) data=[];
    else if(p.endsWith("/recipe-reviews") && req.method()==="GET") data={items:rows,has_more:false};
    else if(p.endsWith("/recipe-reviews") && req.method()==="POST") {
      const body=req.postDataJSON();
      const row={id:"review-1",company_id:companyId,brand_id:brandId,branch_id:branchId,system:"restaurant",source_id:null,created_by:"author",revision:1,status:"draft",proposal:body.proposal,baseline:{},history:[{action:"create",actor_id:"author",reason:body.proposal.reason,at:new Date().toISOString()}]};
      rows=[row]; data=row;
    } else if(p.endsWith("/review-1/actions")) { rows=[{...rows[0],revision:2,status:"submitted"}]; data=rows[0]; }
    return route.fulfill({json:{data,error:null}});
  });
  return writes;
}
test("tablet draft and submit do not activate source; author cannot approve",async({page,context},info)=>{
  const writes=await setup(page);
  await page.setViewportSize({width:820,height:1180}); await page.goto("/company/recipe-reviews");
  await page.getByRole("button",{name:"สร้างร่างสูตรใหม่",exact:true}).click();
  await page.getByLabel("ชื่อสูตร",{exact:true}).fill("หมูย่างสูตรทดลอง");
  await page.getByLabel("สินค้าผลลัพธ์",{exact:true}).selectOption(output);
  await page.getByLabel("วัตถุดิบ 1",{exact:true}).selectOption(ingredient);
  await page.getByLabel("เหตุผลเสนอสูตร",{exact:true}).fill("ทดสอบร่างไม่เปลี่ยนสูตรเดิม");
  await page.getByRole("button",{name:"บันทึกร่าง",exact:true}).click();
  await expect(page.getByRole("button",{name:"ส่งอนุมัติ",exact:true})).toBeVisible();
  await page.getByLabel("เหตุผลการดำเนินการ").fill("ขอครัวกลางตรวจ");
  await page.getByRole("button",{name:"ส่งอนุมัติ",exact:true}).click();
  await expect(page.getByRole("heading",{name:"หมูย่างสูตรทดลอง · รออนุมัติ",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"อนุมัติเนื้อหา (ยังไม่เปิดใช้)",exact:true})).toHaveCount(0);
  expect(await page.getByTestId("recipe-reviews").evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await page.screenshot({path:info.outputPath("reviews-tablet.png"),fullPage:true});
  await context.setOffline(true); await expect(page.getByRole("status")).toContainText("ออฟไลน์");
  await expect(page.getByRole("button",{name:"สร้างร่างสูตรใหม่",exact:true})).toHaveCount(0);
  expect(writes).toEqual(["/api/v1/company/recipe-reviews","/api/v1/company/recipe-reviews/review-1/actions"]);
});
for(const mode of ["error","mismatch"]) test(`review ${mode} fails closed`,async({page})=>{
  await setup(page,mode); await page.goto("/company/recipe-reviews");
  await expect(page.getByRole("alert")).toContainText("อ่านข้อมูลไม่ได้");
  await expect(page.getByRole("button",{name:"สร้างร่างสูตรใหม่",exact:true})).toHaveCount(0);
});
