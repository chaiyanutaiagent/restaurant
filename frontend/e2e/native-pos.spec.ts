import { test, expect, type Page } from '@playwright/test';
import QRCode from 'qrcode';
test('printer raster is split into bounded bands with one final feed and cut', async ({page}) => {
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const modulePath='/src/lib/escPosPrinter.ts';
    const {canvasToEscPosRaster}=await import(modulePath);
    const canvas=document.createElement('canvas'); canvas.width=576; canvas.height=130;
    const context=canvas.getContext('2d')!; context.fillStyle='black'; context.fillRect(0,0,576,130);
    const bytes=canvasToEscPosRaster(canvas); let offset=2; const rows=[]; let pixelCount=0;
    while(offset<bytes.length-7) {
      if(bytes[offset]!==29||bytes[offset+1]!==118)throw Error('Bad raster header');
      const width=bytes[offset+4]+256*bytes[offset+5], height=bytes[offset+6]+256*bytes[offset+7];
      rows.push(height); const pixels=bytes.slice(offset+8,offset+8+width*height);
      if(!pixels.every((b:number)=>b===255))throw Error('Raster data changed');
      pixelCount+=pixels.length; offset+=8+width*height;
    }
    return {rows,pixelCount,tail:Array.from(bytes.slice(offset))};
  });
  expect(result).toEqual({rows:[64,64,2],pixelCount:72*130,tail:[27,100,4,29,86,65,16]});
});
const product=process.env.FCS_POS_PRODUCT!;
test('Retail native intake creates a unit inline and saves one option without backoffice', async ({page}) => {
  test.skip(product!=='retail');
  await mocks(page);await page.goto('/');await login(page);
  await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  await page.evaluate(async ({token,company})=>{const path='/src/native-pos/session.ts';const s=await import(path);s.useAuthStore.getState().setSession(token,company);await s.flushNativeSession();},{token:tokens(false,true,['inventory.product.create','inventory.product.view']),company});
  await page.route('**/api/v1/products/retail/intake-lookup**',r=>r.fulfill({json:{data:{product:null}}}));
  const unitId='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';let unitCreates=0;let body='';
  await page.route('**/api/v1/units',r=>{
    if(r.request().method()==='POST'){unitCreates++;return r.fulfill({status:201,json:{data:{...r.request().postDataJSON(),id:unitId}}});}
    return r.fulfill({json:{data:[]}});
  });
  await page.route('**/api/v1/products/retail/intake',r=>{body=r.request().postData()??'';return r.fulfill({json:{data:{product_id:unitId,name:'เลย์',created:true,qty_received:'0'}}});});
  await page.goto('/retail/products/scan');
  await page.getByLabel('บาร์โค้ดสินค้า',{exact:true}).fill('8851234567890');
  await page.getByRole('button',{name:'ตรวจบาร์โค้ด',exact:true}).click();
  await page.getByLabel('ชื่อสินค้า',{exact:true}).fill('เลย์');
  await page.getByLabel('รูปแบบสินค้า',{exact:true}).selectOption('variant');
  await expect(page.getByLabel(/^ชื่อกลุ่มตัวเลือก/)).toHaveCount(0);
  await page.getByLabel('ค่าตัวเลือก 1',{exact:true}).fill('ซาวครีม');
  await page.getByRole('button',{name:'+ เพิ่มหน่วยสินค้า',exact:true}).click();
  await page.getByLabel('ชื่อหน่วยสินค้าใหม่',{exact:true}).fill('ถุง');
  await page.getByRole('button',{name:'บันทึกหน่วยและเลือกใช้',exact:true}).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByLabel('หน่วยสินค้า',{exact:true})).toHaveValue(unitId);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole('button',{name:'บันทึกสินค้าและสต๊อก',exact:true}).click();
  await expect(page.getByRole('heading',{name:'บันทึกเรียบร้อย'})).toBeVisible();
  expect(unitCreates).toBe(1);expect(body).toContain('"attributes":{"แบบ":"ซาวครีม"}');expect(body).toContain('"unit_id":"'+unitId+'"');
});
const businessType=product==='retail'?'retail_pos':'restaurant';
const origin=product==='retail'?'https://uat-retail.foodchainservice.com':'https://uat-pos.foodchainservice.com';
const company='11111111-1111-4111-8111-111111111111';
const branch='22222222-2222-4222-8222-222222222222';
const brand='33333333-3333-4333-8333-333333333333';
function tokens(superuser=false, scoped=true, permissions:string[]=[]){
  const user={id:'44444444-4444-4444-8444-444444444444',company_id:company,username:'employee',display_name:'พนักงานทดสอบ',is_superuser:superuser};
  const claims={company_id:company,brand_id:scoped?brand:null,branch_id:scoped?branch:null,business_type:scoped?businessType:null,target_database:scoped?businessType:null,permissions,exp:Math.floor(Date.now()/1000)+3600};
  return {access_token:`fixture.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.signature`,refresh_token:'fixture-refresh',user,business_slug:'test-business'};
}
async function mocks(page:Page,superuser=false,scoped=true){
  const requests:string[]=[];
  await page.route(`${origin}/api/v1/**`,async route=>{
    const p=new URL(route.request().url()).pathname;requests.push(p);
    let data:unknown=[];
    if(p.includes('/membership/businesses/'))data={company_id:company,business_slug:'test-business',name:'Test Business'};
    if(p.endsWith('/auth/login'))data=tokens(superuser,scoped);
    if(p.endsWith('/system/me/branches'))data=[{branch_id:branch,brand_id:brand,branch_name:'สาขาทดสอบ',business_type:businessType,target_database:businessType,station_key:null},{branch_id:'other',business_type:'takeaway',target_database:'takeaway',branch_name:'Other product'}];
    if(p.endsWith('/auth/switch-branch'))data=tokens();
    await route.fulfill({json:{data,error:null,meta:{}}});
  });return requests;
}
async function login(page:Page){
  await page.getByLabel('รหัสธุรกิจ',{exact:true}).fill('test-business');
  await page.getByLabel('ชื่อผู้ใช้',{exact:true}).fill('employee');
  await page.getByLabel('รหัสผ่าน',{exact:true}).fill('fixture-password');
  await page.getByRole('button',{name:'เข้าสู่ระบบ',exact:true}).click();
}
test('pairing QR image and app link require matching staff context and explicit confirmation', async ({page}) => {
  await mocks(page);
  let pairs = 0;
  await page.route('**/api/v1/device-auth/pair', async route => {
    pairs++;
    expect(route.request().postDataJSON()).toMatchObject({company_id:company,device_code:'C-TEST123456',pairing_pin:'123456'});
    await route.fulfill({json:{data:{access_token:'device-fixture',refresh_token:'device-refresh',expires_in:3600,
      device:{device_id:company,company_id:company,branch_id:branch,brand_id:brand,device_code:'C-TEST123456',device_type:'counter',business_type:businessType,target_database:businessType}}}});
  });
  const query = new URLSearchParams({company_id:company,branch_id:branch,device_code:'C-TEST123456',pin:'123456',target_app:product,business_code:'test-business',expires_at:new Date(Date.now()+86400000).toISOString()});
  const link = `https://uat-app.foodchainservice.com/device/pair/${product}?${query}`;
  await page.goto('/');
  await page.getByLabel('หรือเลือกภาพ QR').setInputFiles({name:'pair.png',mimeType:'image/png',buffer:await QRCode.toBuffer(link,{width:640})});
  await expect(page.getByRole('status').filter({hasText:'อ่านรหัสเครื่อง C-TEST123456'})).toBeVisible();
  await expect(page.getByLabel('รหัสธุรกิจ',{exact:true})).toHaveCount(0);
  expect(pairs).toBe(0);
  await page.getByLabel('ชื่อผู้ใช้',{exact:true}).fill('employee');
  await page.getByLabel('รหัสผ่าน',{exact:true}).fill('fixture-password');
  await page.getByRole('button',{name:'เข้าสู่ระบบ',exact:true}).click();
  await expect(page.getByLabel('รหัสเครื่อง',{exact:true})).toHaveValue('C-TEST123456');
  await page.evaluate(async link => {const path='/src/native-pos/pairing.ts';const {usePendingPairing}=await import(path);usePendingPairing.getState().receive(link);}, link.replace(company,'99999999-9999-4999-8999-999999999999'));
  await page.getByRole('button',{name:'จับคู่เครื่อง',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('QR ไม่ตรงกับบริษัทหรือสาขา');
  expect(pairs).toBe(0);
  await page.evaluate(async link => {const path='/src/native-pos/pairing.ts';const {usePendingPairing}=await import(path);usePendingPairing.getState().receive(link);}, `foodchainservice-${product}-uat://pair?${query}`);
  expect(pairs).toBe(0);
  await page.getByRole('button',{name:'จับคู่เครื่อง',exact:true}).click();
  await expect(page.getByText('จับคู่สำเร็จแล้ว กลับหน้าขายเพื่อเปิดกะได้')).toBeVisible();
  expect(pairs).toBe(1);
  await page.reload();
  await expect(page.getByText('เครื่องปัจจุบัน: C-TEST123456')).toBeVisible();
});
test('real login only; signed product branch; restart restores session; phone/tablet layout',async({page})=>{
  const requests=await mocks(page,false,false);await page.goto('/');
  await expect(page.getByRole('heading',{name:`Foodchainservice ${product==='retail'?'Retail':'Restaurant'}`})).toBeVisible();
  expect(requests).toEqual([]);
  await login(page);await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  expect(requests).toContain('/api/v1/auth/switch-branch');
  expect(await page.evaluate(()=>localStorage.getItem('erp-auth'))).toBeNull();
  for(const width of [390,820,1280]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
  await page.reload();await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  await page.goto(product==='retail'?'/restaurant/tables':'/retail/pos');
  await expect(page.getByRole('heading',{name:'หน้านี้ไม่เปิดในแอป หรือไม่มีสิทธิ์ใช้งาน'})).toBeVisible();
  expect(requests.some(path=>path.includes('/uat/')||path.includes('/qa/'))).toBe(false);
});
test('reject superadmin and guard wrong-product, unscoped and offline mutations',async({page})=>{
  await mocks(page,true);await page.goto('/');await login(page);
  await expect(page.getByRole('alert')).toContainText('Super Admin');
  const result=await page.evaluate(async(product)=>{
    const modulePath='/src/native-pos/config.ts';const {assertNativeRequest}=await import(modulePath);
    const s={companyId:'company',brandId:'brand',branchId:'branch',businessType:product==='retail'?'retail_pos':'restaurant',targetDatabase:product==='retail'?'retail_pos':'restaurant'};
    const denied=[];
    for(const [path,method,state,online] of [[ '/auth/uat/auto-login','post',s,true ],[product==='retail'?'/restaurant/tables':'/retail/reports/skus','get',s,true],['/pos/sales','post',s,false],['/pos/sales','post',{...s,branchId:null},true]]){
      try{assertNativeRequest(path,method,state,online);denied.push(false);}catch{denied.push(true);}
    }return denied;
  },product);
  expect(result).toEqual([true,true,true,true]);
});
test('Restaurant lost-response recovery keeps exact client id and does not accept offline payment',async({page})=>{
  test.skip(product!=='restaurant','Restaurant-specific online recovery');
  await mocks(page);await page.goto('/');await login(page);await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  const ids:string[]=[];
  await page.route('**/api/v1/restaurant/wap/orders',async route=>{
    ids.push(route.request().postDataJSON().client_order_id);
    if(ids.length===1)return route.abort('failed');
    return route.fulfill({json:{data:{id:'order',queue_display:'001'},error:null}});
  });
  const result=await page.evaluate(async()=>{
    const modulePath='/src/native-pos/paidOrderRecovery.ts';const m=await import(modulePath);
    const payload={items:[{product_id:'p',qty:1}],payment_method:'cash',paid_amount:100};
    let firstFailed=false;try{await m.submitNativeRestaurantOrder(undefined,payload);}catch{firstFailed=true;}
    const pending=await m.hasNativePaymentPending();
    let changedBlocked=false;try{await m.submitNativeRestaurantOrder(undefined,{...payload,paid_amount:200});}catch{changedBlocked=true;}
    const recovered=await m.recoverNativeRestaurantOrder();
    return {firstFailed,pending,changedBlocked,status:recovered.status,remaining:await m.hasNativePaymentPending()};
  });
  expect(result).toEqual({firstFailed:true,pending:true,changedBlocked:true,status:'reconciled',remaining:false});
  expect(ids).toHaveLength(2);expect(ids[0]).toBe(ids[1]);
});

test('durable sale recovery survives restart, blocks changed payload and clears only scoped cart', async ({page}) => {
  await mocks(page); await page.goto('/'); await login(page);
  await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  const payloads: unknown[] = [];
  await page.route('**/api/v1/pos/sales', async route => {
    payloads.push(route.request().postDataJSON());
    if (payloads.length === 1) return route.abort('failed');
    return route.fulfill({json:{data:{id:'sale-original',order_number:'UAT-001',status:'completed',total_amount:100}}});
  });
  await page.evaluate(async () => {
    const storagePath='/src/native-pos/storage.ts', apiPath='/src/lib/api.ts';
    const s=await import(storagePath), {default:api}=await import(apiPath);
    await s.writeNativeCart(`${s.nativeScope()}:counter`, {cartItems:[{product_id:'p',qty:1}]});
    await s.writeNativeCart('another-company:counter', {cartItems:[{product_id:'private',qty:2}]});
    try {await api.post('/pos/sales',{client_order_id:'same-id',items:[{product_id:'p',qty:1}],paid_amount:100});} catch {}
  });
  await page.reload();
  await expect(page.getByRole('heading',{name:'ธุรกรรมรอตรวจสอบ — ห้ามรับเงินซ้ำ'})).toBeVisible();
  // The recovery screen must send the scoped Counter credential too, not just POS.
  await page.evaluate(async ({company,branch,brand,businessType})=>{
    const path='/src/stores/device.store.ts';const {useDeviceStore}=await import(path);
    await useDeviceStore.getState().setSession({access_token:'counter-fixture',refresh_token:'counter-refresh',expires_in:3600,device:{device_id:'counter',device_code:'C01',company_id:company,branch_id:branch,brand_id:brand,business_type:businessType,target_database:businessType,device_type:'counter'}});
  },{company,branch,brand,businessType});
  const recoveryRequest=page.waitForRequest(request=>request.method()==='POST'&&request.url().endsWith('/pos/sales'));
  const blocked=await page.evaluate(async () => {
    const path='/src/lib/api.ts'; const {default:api}=await import(path);
    try {await api.post('/pos/sales',{client_order_id:'different',paid_amount:200});return false;}catch{return true;}
  });
  expect(blocked).toBe(true); expect(payloads).toHaveLength(1);
  await page.getByRole('button',{name:'ตรวจผล / ส่งคำขอเดิม',exact:true}).click();
  expect((await recoveryRequest).headers()['x-device-authorization']).toBe('Bearer counter-fixture');
  await expect(page.getByText(/เอกสาร UAT-001/)).toBeVisible();
  expect(payloads).toHaveLength(2); expect(payloads[0]).toEqual(payloads[1]);
  const carts=await page.evaluate(async () => {
    const path='/src/native-pos/storage.ts'; const s=await import(path);
    return {own:await s.readNativeCart(`${s.nativeScope()}:counter`),other:await s.readNativeCart('another-company:counter')};
  });
  expect(carts.own).toBeNull(); expect(carts.other.cartItems[0].product_id).toBe('private');
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'รับทราบผลที่ยืนยันแล้ว'}).click();
  await expect(page.getByRole('heading',{name:'ธุรกรรมรอตรวจสอบ — ห้ามรับเงินซ้ำ'})).toHaveCount(0);
});

test('assets resolve to fixed UAT host; pending provider payment cannot be acknowledged', async ({page}) => {
  await mocks(page); await page.goto('/'); await login(page);
  await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  await page.route('**/api/v1/pos/sales',route=>route.fulfill({json:{data:{id:'awaiting-bank',status:'pending_payment'}}}));
  const result=await page.evaluate(async () => {
    const apiPath='/src/lib/api.ts', journalPath='/src/native-pos/transactionJournal.ts', assetPath='/src/native-pos/assets.ts';
    const {default:api}=await import(apiPath), j=await import(journalPath), assets=await import(assetPath);
    await api.post('/pos/sales',{client_order_id:'pending-bank',items:[]});
    let denied=false;try {await j.acknowledgeNativeTransaction();}catch{denied=true;}
    return {denied,images:assets.nativeAssetUrls({image_url:'/uploads/product.jpg',nested:[{logo_url:'/uploads/logo.png'}],website:'/not-an-image'})};
  });
  expect(result.denied).toBe(true);
  expect(result.images.image_url).toBe(`${origin}/uploads/product.jpg`);
  expect(result.images.website).toBe('/not-an-image');
});

test('table checkout timeout is inspected, never blindly replayed', async ({page}) => {
  test.skip(product!=='restaurant');
  await mocks(page); await page.goto('/'); await login(page);
  await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  let attempts=0;
  await page.route('**/api/v1/restaurant/sessions/session-one/checkout',route=>{attempts++;return route.abort('failed');});
  await page.route('**/api/v1/restaurant/sessions/session-one/detail',route=>route.fulfill({json:{data:{status:'open',sale_order_id:null}}}));
  const result=await page.evaluate(async () => {
    const a='/src/lib/api.ts', j='/src/native-pos/transactionJournal.ts';
    const {default:api}=await import(a), journal=await import(j);
    try{await api.post('/restaurant/sessions/session-one/checkout',{paid_amount:100});}catch{}
    let stopped=false;try{await journal.recoverNativeTransaction(api);}catch{stopped=true;}
    return {stopped,pending:Boolean(await journal.readNativeTransaction())};
  });
  expect(result).toEqual({stopped:true,pending:true}); expect(attempts).toBe(1);
});

test('native POS restores a scoped cart and provides phone/tablet checkout navigation', async ({page}) => {
  await mocks(page); await page.goto('/'); await login(page);
  await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  const errors:string[]=[]; page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/v1/pos/shifts/current',route=>route.fulfill({json:{data:{id:'shift-one',user_id:'44444444-4444-4444-8444-444444444444',branch_id:branch,location_id:'stock-one',shift_number:'TEST-001',status:'open',version:1,opening_cash:1000}}}));
  await page.route('**/api/v1/stock/locations**',route=>route.fulfill({json:{data:[{id:'stock-one',branch_id:branch,name:'หน้าร้าน'}]}}));
  await page.route('**/api/v1/system/branches/*/settings',route=>route.fulfill({json:{data:{allow_negative_stock:false,pos_require_customer:false}}}));
  await page.route('**/api/v1/crm/settings',route=>route.fulfill({json:{data:{}}}));
  await page.evaluate(async ({token,company})=>{
    const sessionPath='/src/native-pos/session.ts', storagePath='/src/native-pos/storage.ts';
    const session=await import(sessionPath),storage=await import(storagePath);
    session.useAuthStore.getState().setSession(token,company); await session.flushNativeSession();
    await storage.writeNativeCart(`${storage.nativeScope()}:counter`,{cartItems:[{product_id:'water',variant_id:null,product_name:'น้ำดื่มกู้คืน',variant_name:null,sku:'WATER',unit_code:'PCS',qty:2,unit_price:10,original_price:10,discount_amount:0,discount_type:'amount',vat_type:'included',vat_rate:7,subtotal:20,vat_amount:1.31}]});
  },{token:tokens(false,true,['pos.sale.create','pos.sale.view','inventory.product.create','inventory.transfer.view','pos.report.view']),company});
  await page.goto(`/${product}/pos`);
  if (product === 'retail') {
    await expect(page.getByText('Foodchainservice Retail · UAT', {exact:true})).not.toBeVisible();
    await expect(page.getByRole('button',{name:'สแกนเพิ่มสินค้า / รับสต๊อก',exact:true})).not.toBeVisible();
    await expect(page.getByRole('button',{name:'+ เพิ่มหมวดสินค้า',exact:true})).toHaveCount(0);
    const nav=page.getByRole('navigation',{name:'เมนูหลัก Retail'});
    await nav.getByRole('button',{name:'สินค้าและสต๊อก',exact:true}).click();
    await expect(page.getByRole('heading',{name:'สินค้าและสต๊อก',exact:true})).toBeVisible();
    await page.screenshot({path:'/private/tmp/retail-workspace-products-mobile.png',fullPage:true});
    await page.getByRole('button',{name:/^หมวดหมู่สินค้า/}).click();
    await expect(page.getByRole('button',{name:'+ เพิ่มหมวดสินค้า',exact:true})).toBeVisible();
    await expect(page.getByText('ยังไม่มีหมวดสินค้า เริ่มสร้างหมวดแรกได้เลย')).toBeVisible();
    page.once('dialog',dialog=>dialog.accept());
    await nav.getByRole('button',{name:'ขาย',exact:true}).click();
    await expect(page.getByRole('button',{name:/ดูตะกร้า \(2\)/})).toBeVisible();
    await nav.getByRole('button',{name:'บิลและกะ',exact:true}).click();
    await expect(page.getByRole('button',{name:/^ปิดกะและสรุปเงิน/})).toBeVisible();
    await nav.getByRole('button',{name:'เพิ่มเติม',exact:true}).click();
    await nav.getByRole('button',{name:'รายงาน',exact:true}).click();
    await expect(page.getByRole('button',{name:/^รายงานขายตามสินค้า/})).toBeVisible();
    await nav.getByRole('button',{name:'เพิ่มเติม',exact:true}).click();
    await nav.getByRole('button',{name:'ตั้งค่า',exact:true}).click();
    await expect(page.getByRole('button',{name:/^เครื่องขายและเครื่องพิมพ์/})).toBeVisible();
    await nav.getByRole('button',{name:'ขาย',exact:true}).click();
    await page.screenshot({path:'/private/tmp/retail-workspace-sale-mobile.png',fullPage:true});
    const pairingLink = `https://uat-app.foodchainservice.com/device/pair/retail?company_id=${company}&branch_id=${branch}&device_code=C-TEST123456&pin=123456&target_app=retail`;
    await page.getByPlaceholder('สแกนบาร์โค้ด / ค้นหาชื่อ / SKU').fill(pairingLink);
    await page.getByPlaceholder('สแกนบาร์โค้ด / ค้นหาชื่อ / SKU').press('Enter');
    await expect(page.getByText('QR จับคู่เครื่อง',{exact:true})).toBeVisible();
    await expect(page.getByText(pairingLink,{exact:true})).toHaveCount(0);
  }
  await expect(page.getByRole('button',{name:/ดูตะกร้า \(2\)/})).toBeVisible();
  await page.getByRole('button',{name:/ดูตะกร้า \(2\)/}).click();
  await expect(page.getByText('น้ำดื่มกู้คืน',{exact:true})).toBeVisible();
  for(const width of [390,820,1280]) { await page.setViewportSize({width,height:900}); expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true); }
  if(product==='retail')await page.screenshot({path:'/private/tmp/retail-workspace-sale-desktop.png',fullPage:true});
  await page.reload(); await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('button',{name:/ดูตะกร้า \(2\)/})).toBeVisible();
  expect(errors).toEqual([]);
  await page.evaluate(async product=>{
    const modulePath='/src/native-pos/appUpdate.ts';
    const {usePosUpdate}=await import(modulePath);
    usePosUpdate.setState({installed:{packageId:`com.foodchainservice.${product}.uat`,versionCode:10006,versionName:'0.1.0-uat.6'},release:{package_id:`com.foodchainservice.${product}.uat`,version_code:10007,version_name:'0.1.0-uat.7'}});
  },product);
  await expect(page.getByRole('link',{name:'อัปเดตเมื่อพร้อม'})).toBeVisible();
  await expect(page.getByRole('button',{name:'ดาวน์โหลดและติดตั้ง',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:/ดูตะกร้า \(2\)/})).toBeVisible();
  await page.getByRole('link',{name:'อัปเดตเมื่อพร้อม'}).click();
  await expect(page.getByText('มีสินค้าในตะกร้า กรุณาพักบิลหรือทำรายการให้เสร็จก่อนอัปเดต',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:/ดูตะกร้า \(2\)/})).toBeVisible();
  // Navigate through the normal settings path; install itself must recheck too.
  await page.evaluate(()=>{history.pushState({},'', '/native/device');window.dispatchEvent(new PopStateEvent('popstate'));});
  await page.getByRole('button',{name:'ดาวน์โหลดและติดตั้ง',exact:true}).click();
  await expect(page.getByText('มีสินค้าในตะกร้า กรุณาพักบิลหรือทำรายการให้เสร็จก่อนอัปเดต',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'ตรวจอัปเดตแอป',exact:true}).click();
  await expect(page.getByText('ตรวจอัปเดตได้ในแอป Android เท่านั้น',{exact:true})).toBeVisible();
});

test('Retail workspaces preserve stock receipt retry and respect management-only permissions', async ({page}) => {
  test.skip(product !== 'retail');
  await mocks(page);await page.goto('/');await login(page);
  await expect(page.getByRole('heading',{name:'ตั้งค่าเครื่องขาย'})).toBeVisible();
  const permissions=['pos.sale.create','pos.sale.view','inventory.product.create','inventory.stock.adjust','pos.report.view'];
  await page.evaluate(async ({token,company})=>{const path='/src/native-pos/session.ts';const s=await import(path);s.useAuthStore.getState().setSession(token,company);await s.flushNativeSession();},{token:tokens(false,true,permissions),company});
  await page.route('**/api/v1/pos/shifts/current',r=>r.fulfill({json:{data:{id:'shift-one',user_id:'44444444-4444-4444-8444-444444444444',branch_id:branch,location_id:'stock-one',shift_number:'TEST-001',status:'open',version:1,opening_cash:500}}}));
  await page.route('**/api/v1/stock/locations**',r=>r.fulfill({json:{data:[{id:'stock-one',branch_id:branch,name:'คลังหน้าร้าน',code:'ST01',is_active:true}]}}));
  await page.route('**/api/v1/system/branches/*/settings',r=>r.fulfill({json:{data:{allow_negative_stock:false}}}));
  await page.route('**/api/v1/crm/settings',r=>r.fulfill({json:{data:{}}}));
  await page.route('**/api/v1/products/retail/intake-lookup**',r=>r.fulfill({json:{data:{product:{id:'water',name:'น้ำดื่ม',barcode:'8851234567890',sku:'WATER',selling_price:'10',cost_price:'5'}}}}));
  const requestIds:string[]=[];
  await page.route('**/api/v1/products/retail/intake',r=>{
    requestIds.push(r.request().postData()?.match(/"request_id":"([^"]+)"/)?.[1]??'');
    return r.fulfill(requestIds.length===1?{status:500,json:{detail:'uncertain fixture'}}:{json:{data:{product_id:'water',name:'น้ำดื่ม',created:false,qty_received:'3',replayed:true}}});
  });
  await page.goto('/retail/pos?workspace=products');
  await page.getByRole('button',{name:/^รับสต๊อกสินค้าเดิม/}).click();
  await page.getByLabel('บาร์โค้ดสินค้า',{exact:true}).fill('8851234567890');
  await page.getByRole('button',{name:'ตรวจบาร์โค้ด',exact:true}).click();
  await expect(page.getByText('พบสินค้าเดิม — รับเพิ่ม',{exact:true})).toBeVisible();
  await page.getByLabel('จำนวนรับเข้า',{exact:true}).fill('3');
  await page.getByRole('combobox',{name:'คลังรับสินค้า',exact:true}).selectOption('stock-one');
  await page.getByRole('button',{name:'ยืนยันรับสินค้าเดิมเพิ่ม',exact:true}).click();
  await expect(page.getByRole('button',{name:'ลองบันทึกเดิมอีกครั้ง',exact:true})).toBeVisible();
  const nav=page.getByRole('navigation',{name:'เมนูหลัก Retail'});
  await expect(nav.getByRole('button',{name:'ขาย',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'กลับเมนูสินค้าและสต๊อก',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'ลองบันทึกเดิมอีกครั้ง',exact:true}).click();
  await expect(page.getByRole('heading',{name:'บันทึกเรียบร้อย'})).toBeVisible();
  expect(requestIds).toHaveLength(2);expect(requestIds[0]).not.toBe('');expect(requestIds[1]).toBe(requestIds[0]);
  await expect(nav.getByRole('button',{name:'ขาย',exact:true})).toBeEnabled();
  // A product administrator need not have POS sale permission, and must not see reports.
  await page.evaluate(async ({token,company})=>{const path='/src/native-pos/session.ts';const s=await import(path);s.useAuthStore.getState().setSession(token,company);await s.flushNativeSession();},{token:tokens(false,true,['inventory.product.create']),company});
  await page.goto('/retail/workspace/products');
  await expect(page.getByRole('button',{name:/^เพิ่มสินค้า/})).toBeVisible();
  await expect(page.getByRole('button',{name:/^รับสต๊อกสินค้าเดิม/})).toHaveCount(0);
  await expect(page.getByRole('navigation',{name:'เมนูหลัก Retail'}).getByRole('button',{name:'ขาย',exact:true})).toHaveCount(0);
  await page.goto('/retail/workspace/reports');
  await expect(page.getByRole('alert')).toContainText('ไม่มีสิทธิ์เข้าถึงส่วนนี้');
});
