import { test, expect, type Page } from '@playwright/test';
const product=process.env.FCS_POS_PRODUCT!;
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
  },{token:tokens(false,true,['pos.sale.create','pos.sale.view']),company});
  await page.goto(`/${product}/pos`);
  await expect(page.getByRole('button',{name:/ดูตะกร้า \(2\)/})).toBeVisible();
  await page.getByRole('button',{name:/ดูตะกร้า \(2\)/}).click();
  await expect(page.getByText('น้ำดื่มกู้คืน',{exact:true})).toBeVisible();
  for(const width of [390,820,1280]) { await page.setViewportSize({width,height:900}); expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true); }
  await page.reload(); await page.setViewportSize({width:390,height:844});
  await expect(page.getByRole('button',{name:/ดูตะกร้า \(2\)/})).toBeVisible();
  expect(errors).toEqual([]);
});
