# WP77–WP81 — Takeaway Store Operating Model

วันที่: 2026-09-27

สถานะ: **uat_deployed — automated gate passed; physical UAT deferred**

## ขอบเขต

- Takeaway สาขาเล็กใช้ `counter_combined`: พนักงานคนเดียวขาย รับเงิน เตรียม เรียกคิว และส่งมอบ
- Takeaway สาขาใหญ่เลือก `separate_stations` และเปิดหน้าจุดเตรียมสินค้าแยกได้
- จำนวนพนักงานต่อสาขาไม่จำกัด และกำหนด `Branch Manager` เป็นหัวหน้าสาขาได้
- ครัวกลาง/การผลิตส่วนกลางยังแยกจากงานหน้าร้าน
- Restaurant POS และ Retail POS ไม่เปลี่ยน workflow

## สิ่งที่ส่งมอบ

1. เพิ่ม role preset `Takeaway Store Operator` แบบ Branch scope สำหรับขาย เตรียม ส่งมอบ เปิด/ปิดกะ สั่ง/รับของ และดูสต๊อกสาขา
2. ถอนสิทธิ์ Takeaway ออกจาก Restaurant Kitchen Manager/Kitchen Staff เพื่อไม่ให้บทบาทข้ามผลิตภัณฑ์
3. เพิ่ม fulfillment API ระดับออเดอร์ `queued -> preparing -> ready -> picked_up` และบันทึกผู้ปฏิบัติงานลง fulfillment history/outbox
4. หน้าขาย Takeaway รวมรายการเตรียมและส่งมอบไว้ในจอเดียว พร้อมเปลี่ยนข้อความจาก “ส่งครัว” เป็น “เตรียมสินค้า”
5. หน้าแยก `/takeaway/store/fulfillment` แสดงเฉพาะเมื่อแบรนด์ตั้ง `takeaway_fulfillment_mode=separate_stations`
6. URL เก่า `/takeaway/store/kitchen`, `/takeaway/store/pickup`, `/takeaway/kitchen`, `/takeaway/pickup` redirect ไป fulfillment route
7. Chambo BKK-01 ตั้ง `counter_combined`
8. ข้อมูลทดสอบ Chambo เปลี่ยนเป็นหัวหน้าสาขา 1 คนและ Store Operator 3 คน; บัญชีตำแหน่งครัว/คลัง/แคชเชียร์เดิมถูกจัดเป็น superseded

## Chambo UAT staff target

| Username | ตำแหน่ง |
| --- | --- |
| `test.chambo.brand-manager` | ผู้จัดการแบรนด์ |
| `test.chambo.area-manager` | ผู้จัดการเขต |
| `test.chambo.branch-manager` | หัวหน้าสาขา |
| `test.chambo.operator01` | พนักงานหน้าร้าน Takeaway |
| `test.chambo.operator02` | พนักงานหน้าร้าน Takeaway |
| `test.chambo.operator03` | พนักงานหน้าร้าน Takeaway |

รหัสผ่านทดสอบส่งผ่าน environment แบบครั้งเดียวและไม่บันทึกลง Git

## Automated gate

- Backend focused unit/policy tests: `31` ผ่าน
- Frontend type-check: ผ่าน
- Takeaway browser tests: `6/6` ผ่าน
- `git diff --check`: ผ่าน

## UAT deployment evidence

- Source commit: `78aee14`
- Backend image: `restaurant-pos-backend:wp81-78aee14`
- Frontend image: `restaurant-pos-frontend:wp81-78aee14`
- Backend health: `healthy`
- Public smoke: HTTP `200` สำหรับ readiness, Restaurant POS, Retail POS, Takeaway sale และ Takeaway fulfillment
- Chambo: แบรนด์ `chambo`, สาขา `BKK-01` (โอโซนวัน), fulfillment mode `counter_combined`
- Test staff: active `33` บัญชีทั้งบริษัท; Chambo active `6` บัญชี และบัญชีหน้าที่เดิม 5 บัญชีถูกปิดใช้งาน
- Takeaway data retained: หมวดหมู่ `12`, สินค้า `45`, รายการสาขา `16`, จุดสต๊อก `5`, สูตร `8`
- `TAKEAWAY_UAT_TRANSACTION_WRITES_ENABLED=false`; ไม่เปิด Production

## Rollback

- Backup path: `/home/behappyaiagent/restaurant-uat-deploy-backups/wp77-81-before-78aee14`
- Custom-format dumps ครบ 5 ฐานข้อมูล; checksum และ `pg_restore --list` ผ่านทั้งหมด
- Production containers และ UAT PostgreSQL/Redis/Nginx/Cloudflare Tunnel มี container ID เดิมหลัง deploy
- Rollback ใช้ image เดิม `restaurant-pos-backend:wp74-f8b6d24` และ `restaurant-pos-frontend:wp72-b18b2ac` พร้อมฐานข้อมูลชุดสำรองข้างต้น

## Release boundary

- Deploy เฉพาะ UAT
- ไม่เปิด Production flags
- Takeaway transaction gate และ Production activation คงค่าตามเดิม
- Physical Android/printer/cash/PromptPay/network-loss UAT ยังข้ามตามคำสั่งผู้ใช้
- ไม่แก้ `/Users/user/Projects/erp-pos-run`
