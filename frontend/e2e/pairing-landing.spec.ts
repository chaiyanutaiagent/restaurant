import { test, expect } from '@playwright/test';
test('Android gets the matching app and download; desktop stays on web; GET never consumes PIN', async ({page}) => {
  let posts = 0;
  await page.route('**/api/v1/**', route => { if(route.request().method()==='POST') posts++;return route.fulfill({json:{data:[]}}); });
  await page.addInitScript(() => Object.defineProperty(navigator,'userAgent',{get:()=> 'Mozilla/5.0 (Linux; Android 15) Chrome/130'}));
  for (const product of ['restaurant','retail','takeaway']) {
    const name = product[0].toUpperCase()+product.slice(1);
    await page.goto(`/device/pair/${product}?company_id=11111111-1111-4111-8111-111111111111&device_code=C-ABCDEFGH&pin=123456&target_app=${product}&expires_at=${encodeURIComponent(new Date(Date.now()+86400000).toISOString())}`);
    await expect(page.getByRole('link',{name:`เปิดแอป ${name} บน Android`})).toHaveAttribute('href',new RegExp(`package=com.foodchainservice.${product}.uat;`));
    await expect(page.getByRole('link',{name:`ยังไม่มีแอป / อัปเดต — ดาวน์โหลด ${name}`})).toHaveAttribute('href',new RegExp(`foodchainservice-${product}.*\\.apk$`));
    await expect(page.getByRole('button',{name:'จับคู่และเปิด Workspace'})).toHaveCount(0);
    await page.getByRole('button',{name:'ใช้ผ่านเว็บแทน'}).click();
    await expect(page.getByRole('button',{name:'จับคู่และเปิด Workspace'})).toBeEnabled();
  }
  expect(posts).toBe(0);
  await page.goto('/device/pair/retail?target_app=retail&expires_at=2020-01-01');
  await expect(page.getByRole('alert')).toContainText('ลิงก์หมดอายุ');
  await expect(page.getByRole('link',{name:'เปิดแอป Retail บน Android'})).toHaveCount(0);
});
