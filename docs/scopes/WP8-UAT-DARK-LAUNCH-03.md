# WP8-UAT-DARK-LAUNCH-03 — UAT Boundary Deployment Evidence

วันที่ดำเนินการ: 2026-09-16

สถานะ: **passed — WP8 UAT dark launch พร้อม rollback; Retail traffic ยังอยู่ Legacy**

## ขอบเขตที่อนุมัติ

- deploy release `df12dccd2558aef55edadde9c1e0de675d534262` ไปที่
  `https://uat-pos.foodchainservice.com`
- freeze UAT writes และสร้าง backup ก่อนเปลี่ยน schema/runtime
- สร้าง physical database แยกสำหรับ Platform, Restaurant, Retail และ Takeaway
- เปิด `IDENTITY_DATABASE=platform_core` และ reference projector ใน UAT
- คง `RESTAURANT_SERVICE_DATABASE=legacy` และ `RETAIL_SERVICE_DATABASE=legacy`
- ไม่แตะ Chambo/ERP-POS stack และไม่ deploy Production

## Preflight และ backup

- ทำ advanced-Legacy restore/migration rehearsal บนฐานชั่วคราวก่อน cutover จริง
- rehearsal ผ่านทั้งห้า migration heads, Platform parity และ startup health
- Retail activation guard ปฏิเสธการเปิดเมื่อไม่มี Retail Brand ตามที่ออกแบบไว้
- final backup อยู่ที่
  `/home/behappyaiagent/backups/restaurant-uat-wp8/final-cutover-20260916T034528Z`
- Legacy, uploads และ Redis ก่อน cutover ตรวจ SHA-256 และอ่าน archive ได้
- Legacy/Platform/Restaurant/Retail/Takeaway dumps หลัง cutover ตรวจ SHA-256 และ
  `pg_restore --list` ได้ทุกไฟล์

## Migration heads หลัง deploy

| Boundary | Database | Head |
| --- | --- | --- |
| Legacy rollback source | `restaurant_uat_db` | `p14dist0016` |
| Platform | `restaurant_platform_core_db` | `p13platform0017` |
| Restaurant standby | `restaurant_ops_db` | `p6restaurant0007` |
| Retail standby | `retail_ops_db` | `p8retail0002` |
| Takeaway standby | `takeaway_ops_db` | `p6takeaway0004` |

## Reconciliation

Platform → Restaurant reference parity หลัง deploy:

- Company `1/1`
- Branch `2/2`
- User `1/1`
- Brand `0/0`
- BrandBranch `0/0`
- mismatch `0`; failed projection `0`

ข้อมูล Restaurant ใน Legacy หลัง cutover:

- Category `4`
- Product `16`
- Stock balance `16`
- Dining table `16`
- Sale order `0`

## Runtime verification

- backend/frontend/Nginx ใช้ image tag `wp8-df12dcc`
- PostgreSQL, Redis และ backend healthy; container ไม่มี restart/error หลัง deploy
- `/`, `/pos`, `/admin`, `/health` และ `/health/ready` ตอบ `200`
- UAT auto-login ผ่าน `200` หลัง identity cutover
- Platform projection replay หลัง auto-login มี mismatch `0`

## เหตุผลที่ยังไม่เปิด Retail routing

UAT มี Brand `0` จึงไม่มี Retail Company/Brand/Branch/Product/Stock Location ที่ถูกต้องสำหรับ selective
migration. ระบบพิสูจน์แล้วว่าจะ fail closed หากตั้ง `RETAIL_SERVICE_DATABASE=retail` ในสถานะนี้ จึงคง
Retail ที่ Legacy และไม่สร้างข้อมูลลูกค้าปลอมเพื่อข้าม gate

## Rollback

1. ตั้ง `IDENTITY_DATABASE=legacy`, `REFERENCE_PROJECTOR_ENABLED=false` และ
   `RETAIL_SERVICE_DATABASE=legacy`
2. recreate backend ด้วย image เดิม `restaurant-pos-backend:uat-p5-hardening-41d49d3`
3. คงฐาน boundary และ dumps หลัง cutoverไว้เพื่อ audit; ห้ามลบเมื่อเริ่มมี Retail data
4. restore `legacy-before.dump`, uploads และ Redis เฉพาะเมื่อ additive rollback ไม่เพียงพอ

## งานที่ยังค้าง

- physical scanner/printer/cash drawer/offline UAT
- สร้าง Retail test tenant จริงที่มี Brand/Branch/Product/Stock Location
- selective migration, count/digest/amount/stock reconciliation และ owner sign-off
- เปลี่ยน Retail routing ใน UAT แล้วเฝ้าระวังตามช่วง cutover
- Production go/no-go และ activation
