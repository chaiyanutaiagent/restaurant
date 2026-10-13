import { test, expect, type Page } from "@playwright/test";
import QRCode from "qrcode";

const company="11111111-1111-4111-8111-111111111111", brand="22222222-2222-4222-8222-222222222222", branch="33333333-3333-4333-8333-333333333333";
const unit="44444444-4444-4444-8444-444444444444", location="55555555-5555-4555-8555-555555555555", product="66666666-6666-4666-8666-666666666666";
async function setup(page:Page, existing=false, retry=false) {
  await page.setViewportSize({width:1024,height:768});
  await page.addInitScript(({company,brand,branch})=>{
    localStorage.setItem("erp-auth",JSON.stringify({state:{accessToken:"fixture-token",refreshToken:"fixture-refresh",companyId:company,brandId:brand,branchId:branch,businessType:"retail_pos",targetDatabase:"retail_pos",permissions:["*"],scopeTypes:["company","branch"],user:{id:company,company_id:company,username:"tester",is_active:true}},version:0}));
  },{company,brand,branch});
  const submissions:string[]=[];
  await page.route("**/api/v1/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    const ok=(data:unknown)=>route.fulfill({contentType:"application/json",body:JSON.stringify({data,meta:{},error:null})});
    if(path.endsWith("/units"))return ok([{id:unit,name:"ชิ้น",is_active:true}]);
    if(path.endsWith("/categories"))return ok([]);
    if(path.endsWith("/stock/locations"))return ok([{id:location,branch_id:branch,code:"SHOP",name:"หน้าร้าน",is_active:true}]);
    if(path.endsWith("/intake-lookup"))return ok({product:existing?{id:product,name:"น้ำดื่ม",barcode:"000123",sku:"WATER",selling_price:"10",cost_price:"5"}:null});
    if(path.endsWith("/intake")){
      submissions.push(route.request().postData()??"");
      if(retry&&submissions.length===1)return route.fulfill({status:503,body:"unavailable"});
      return ok({product_id:product,name:"น้ำดื่ม",created:!existing,qty_received:"10",replayed:retry});
    }
    return ok([]);
  });
  await page.goto("/retail/products/scan");
  await page.getByLabel("บาร์โค้ดสินค้า").fill("000123");
  await page.getByRole("button",{name:"ตรวจบาร์โค้ด",exact:true}).click();
  return submissions;
}

test("retail intake creates a product with photo and opening stock on tablet",async({page})=>{
  const submissions=await setup(page);
  await page.getByLabel("ชื่อสินค้า",{exact:true}).fill("น้ำดื่ม");
  await page.getByLabel("หน่วยสินค้า",{exact:true}).selectOption(unit);
  await page.getByLabel("ราคาขาย (บาท)",{exact:true}).fill("10");
  await page.getByLabel("ต้นทุนต่อหน่วย (บาท)",{exact:true}).fill("5");
  await page.getByLabel("จำนวนรับเข้า",{exact:true}).fill("10");
  await page.getByLabel("คลังรับสินค้า",{exact:true}).selectOption(location);
  await page.getByLabel("แนบรูป",{exact:true}).setInputFiles({name:"water.png",mimeType:"image/png",buffer:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1V8AAAAASUVORK5CYII=","base64")});
  await expect(page.getByAltText("รูปสินค้าก่อนบันทึก")).toBeVisible();
  await page.getByRole("button",{name:"บันทึกสินค้าและสต๊อก",exact:true}).click();
  await expect(page.getByRole("heading",{name:"บันทึกเรียบร้อย"})).toBeVisible();
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).toContain('"barcode":"000123"');
  expect(submissions[0]).toContain('filename="water.png"');
  expect(submissions[0]).toContain(location);
});

test("retail intake existing barcode receives stock without changing sale price and retries same request",async({page})=>{
  const submissions=await setup(page,true,true);
  await expect(page.getByLabel("ชื่อสินค้า",{exact:true})).toBeDisabled();
  await expect(page.getByLabel("ราคาขาย (บาท)",{exact:true})).toBeDisabled();
  await expect(page.getByLabel("แนบรูป",{exact:true})).toHaveCount(0);
  await page.getByLabel("คลังรับสินค้า",{exact:true}).selectOption(location);
  await page.getByRole("button",{name:"ยืนยันรับสินค้าเดิมเพิ่ม",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("ยังยืนยันผลบันทึกไม่ได้");
  await expect(page.getByLabel("จำนวนรับเข้า",{exact:true})).toBeDisabled();
  await page.getByRole("button",{name:"ลองบันทึกเดิมอีกครั้ง",exact:true}).click();
  await expect(page.getByRole("heading",{name:"บันทึกเรียบร้อย"})).toBeVisible();
  expect(submissions).toHaveLength(2);
  const ids=submissions.map(body=>body.match(/"request_id":"([^"]+)"/)?.[1]);
  expect(ids[0]).toBeTruthy();expect(ids[0]).toBe(ids[1]);
  expect(submissions[0]).toContain('"existing_product_id":"'+product+'"');
});

test("retail intake goes offline without submitting",async({page,context})=>{
  const submissions=await setup(page);
  await context.setOffline(true);
  await expect(page.getByRole("alert")).toContainText("ต้องออนไลน์");
  await expect(page.getByRole("button",{name:"บันทึกสินค้าและสต๊อก",exact:true})).toBeDisabled();
  expect(submissions).toHaveLength(0);
});

test("retail intake scanner reads simulated camera and releases its stream",async({page})=>{
  await setup(page);
  const dataUrl=await QRCode.toDataURL("000123",{width:480,margin:5});
  await page.evaluate(async(dataUrl)=>{
    const image=new Image();image.src=dataUrl;await image.decode();
    const canvas=document.createElement("canvas");canvas.width=640;canvas.height=480;
    const ctx=canvas.getContext("2d")!;ctx.fillStyle="white";ctx.fillRect(0,0,640,480);ctx.drawImage(image,80,0);
    const stream=canvas.captureStream(10);
    (window as unknown as {testCameraStream:MediaStream}).testCameraStream=stream;
    Object.defineProperty(navigator.mediaDevices,"getUserMedia",{configurable:true,value:async()=>stream});
  },dataUrl);
  await page.getByLabel("บาร์โค้ดสินค้า").fill("");
  await page.getByRole("button",{name:"เปิดกล้องสแกน",exact:true}).click();
  await expect(page.getByLabel("บาร์โค้ดสินค้า",{exact:true})).toHaveValue("000123");
  await expect(page.getByRole("heading",{name:"สินค้าใหม่ — รายละเอียดและราคา"})).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await page.evaluate(()=>(window as unknown as {testCameraStream:MediaStream}).testCameraStream.getTracks().every(track=>track.readyState==="ended"))).toBe(true);
});
