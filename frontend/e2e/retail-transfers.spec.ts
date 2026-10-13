import { test, expect, type Page } from "@playwright/test";

const company="11111111-1111-4111-8111-111111111111",brand="22222222-2222-4222-8222-222222222222",branch="33333333-3333-4333-8333-333333333333";
const warehouse="44444444-4444-4444-8444-444444444444",source="55555555-5555-4555-8555-555555555555",dest="66666666-6666-4666-8666-666666666666";
const initial={id:"order",to_number:"TO-TEST-1",version:4,status:"in_transit",from_branch_id:warehouse,to_branch_id:branch,from_branch_name:"คลัง Retail",to_branch_name:"ร้าน 1",requested_by:company,note:"",items:[{id:"item",product_name:"เสื้อ ดำ M",sku:"BLACK-M",qty_requested:"10",qty_approved:"10",qty_sent:"10",qty_received:"0",qty_in_transit:"10",qty_discrepancy:"0"}]};

async function setup(page:Page,mode:"retry"|"create"|"stale"|"warehouse"="retry"){
  await page.setViewportSize({width:390,height:844});
  await page.addInitScript(({company,brand,branch})=>localStorage.setItem("erp-auth",JSON.stringify({state:{accessToken:"fixture-token",refreshToken:"fixture-refresh",companyId:company,brandId:brand,branchId:branch,businessType:"retail_pos",targetDatabase:"retail_pos",permissions:["*"],scopeTypes:["company","branch"],user:{id:company,company_id:company,username:"tester",is_active:true}},version:0})),{company,brand,branch:mode==="warehouse"?warehouse:branch});
  const sent:Record<string,unknown>[]=[];
  let order=structuredClone(initial);
  await page.route("**/api/v1/**",async route=>{
    const path=new URL(route.request().url()).pathname;
    const ok=(data:unknown)=>route.fulfill({contentType:"application/json",body:JSON.stringify({data})});
    if(path.endsWith("/options"))return ok([{id:source,name:"คลัง",branch_id:warehouse,branch_name:"คลัง Retail",is_warehouse:true},{id:dest,name:"หน้าร้าน",branch_id:branch,branch_name:"ร้าน 1",is_warehouse:false}]);
    if(path.endsWith("/stock"))return ok([{product_id:"product",variant_id:"variant",name:"เสื้อ ดำ M",sku:"BLACK-M",available:"20"}]);
    if(path.endsWith("/commands")){
      const body=route.request().postDataJSON();sent.push(body);
      if(mode==="retry"&&sent.length===1)return route.fulfill({status:503,body:"unavailable"});
      if(mode==="stale"){order={...order,version:5,status:"partially_received",items:[{...order.items[0],qty_received:"2",qty_in_transit:"8"}]};return route.fulfill({status:409,contentType:"application/json",body:JSON.stringify({detail:"ใบโอนเปลี่ยนแปลงแล้ว"})});}
      order={...order,version:5,status:"partially_received",items:[{...order.items[0],qty_received:"4",qty_in_transit:"6"}]};return ok(order);
    }
    if(path.endsWith("/transfers")){
      if(route.request().method()==="POST"){sent.push(route.request().postDataJSON());order={...order,version:1,status:"draft"};return ok(order);}
      return ok({orders:mode==="create"&&sent.length===0?[]:[order],has_more:false});
    }
    if(path.endsWith("/transfers/order"))return ok(order);
    return ok([]);
  });
  await page.goto("/retail/transfers");
  return sent;
}

test("partial receipt retries exact request, locks editing, renders on phone/tablet/desktop",async({page})=>{
  const sent=await setup(page);
  await page.getByRole("button",{name:/TO-TEST-1/}).click();
  await page.getByLabel("ยอดรับสะสม BLACK-M",{exact:true}).fill("4");
  for(const width of [320,820,1440]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
  await page.getByRole("button",{name:"ยืนยันรับสินค้า",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("ยังยืนยันผลไม่ได้");
  await expect(page.getByLabel("ยอดรับสะสม BLACK-M",{exact:true})).toBeDisabled();
  await page.getByRole("button",{name:"ลองคำขอเดิมอีกครั้ง",exact:true}).click();
  await expect(page.getByRole("heading",{name:/TO-TEST-1 · รับบางส่วน/})).toBeVisible();
  await expect(page.getByLabel("ยอดรับสะสม BLACK-M",{exact:true})).toHaveValue("4");
  expect(sent).toHaveLength(2);expect(sent[0]).toEqual(sent[1]);expect(sent[0]).toMatchObject({expected_version:4,action:"receive",finalize:false,items:[{item_id:"item",quantity:"4"}]});
  await page.screenshot({path:"/private/tmp/restaurant-retail-transfer-desktop.png",fullPage:true});
});

test("create variant transfer draft without posting stock",async({page})=>{
  const sent=await setup(page,"create");
  await page.getByRole("button",{name:"+ สร้างใบโอน",exact:true}).click();
  await page.getByLabel("คลังต้นทาง",{exact:true}).selectOption(source);
  await page.getByLabel("คลังปลายทาง",{exact:true}).selectOption(dest);
  await page.getByRole("button",{name:/เสื้อ ดำ M · BLACK-M/}).click();
  await page.getByLabel("จำนวน BLACK-M",{exact:true}).fill("6");
  await page.getByRole("button",{name:"บันทึกร่าง",exact:true}).click();
  await expect(page.getByRole("heading",{name:/TO-TEST-1 · ร่าง/})).toBeVisible();
  expect(sent[0]).toMatchObject({from_location_id:source,to_location_id:dest,items:[{product_id:"product",variant_id:"variant",qty_requested:"6"}]});
});

test("stale receipt reloads current version; short closure requires note; offline prevents writes",async({page,context})=>{
  const sent=await setup(page,"stale");
  await page.getByRole("button",{name:/TO-TEST-1/}).click();
  await page.getByLabel("ปิดรับใบนี้",{exact:false}).check();
  await page.getByRole("button",{name:"ยืนยันรับสินค้า",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("กรุณาระบุเหตุผล");expect(sent).toHaveLength(0);
  await page.getByLabel("ปิดรับใบนี้",{exact:false}).uncheck();
  await page.getByLabel("ยอดรับสะสม BLACK-M",{exact:true}).fill("4");
  await page.getByRole("button",{name:"ยืนยันรับสินค้า",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("ใบโอนเปลี่ยนแปลงแล้ว");
  await expect(page.getByLabel("ยอดรับสะสม BLACK-M",{exact:true})).toHaveValue("2");
  await context.setOffline(true);
  await expect(page.getByRole("button",{name:"ยืนยันรับสินค้า",exact:true})).toBeDisabled();
  expect(sent).toHaveLength(1);
});

test("warehouse cannot receive its own shipment",async({page})=>{
  await setup(page,"warehouse");
  await page.getByRole("button",{name:/TO-TEST-1/}).click();
  await expect(page.getByRole("heading",{name:/TO-TEST-1 · ระหว่างทาง/})).toBeVisible();
  await expect(page.getByRole("button",{name:"ยืนยันรับสินค้า",exact:true})).toHaveCount(0);
});

test("SKU report filters and exports current page without horizontal page overflow",async({page})=>{
  await setup(page);
  await page.route("**/retail/reports/skus?**",route=>route.fulfill({contentType:"application/json",body:JSON.stringify({data:{page:1,total:1,generated_at:new Date().toISOString(),rows:[{product_id:"p",variant_id:"v",product_name:"เสื้อ",variant_name:"ดำ / M",sku:"BLACK-M",barcode:"TEST-1",product_brand_name:"UAT Wear",active:true,on_hand:10,reserved:2,available:8,incoming:3,outgoing:0,sold:5,returned:1,net_quantity:4,line_subtotal:995,refund_amount:199}]}})}));
  await page.goto("/retail/reports/skus");
  await expect(page.getByRole("cell",{name:"ดำ / M",exact:true})).toBeVisible();
  await page.getByLabel("ค้นหาสินค้า / แบรนด์ / ตัวเลือก / บาร์โค้ด").fill("UAT Wear");
  for(const width of [320,820,1440]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
  const download=page.waitForEvent("download");
  await page.getByRole("button",{name:"ดาวน์โหลด CSV หน้านี้",exact:true}).click();
  expect((await download).suggestedFilename()).toContain("retail-sku-");
});
