# WP7-RETAIL-SAAS-ALIGNMENT-01 — Retail POS SaaS Alignment Foundation

วันที่อนุมัติและเริ่มทำ: 2026-09-15

สถานะ: **completed_local — WP7-A ถึง WP7-D ผ่าน automated local gate; Retail runtime และ data cutover ยังปิด**

Baseline rollback: WP6 commit `d9e4a728ef6316366a88e3e1592f268164aae846`

## เป้าหมาย

จัด Retail POS เดิมให้มี Company/Brand/Branch, Device และ database boundary ตามมาตรฐาน
Foodchainservice โดยรักษาหน้าขายและข้อมูลเดิมบน Legacy ไว้ก่อน แล้วสร้างเส้นทางถอยกลับที่ชัดเจน
สำหรับการย้าย Retail จริงใน WP8

## WP7-A — Current-state audit และ ownership

- [x] ยืนยัน `retail_pos` เป็น canonical `business_type` และ `target_database`
- [x] ตรวจ Product/Barcode/Stock/Shift/Sale/Payment/Receipt เดิมที่ยังอยู่ Legacy
- [x] ระบุ Platform เป็น owner ของ Company/Brand/Branch/User/Assignment/Device/Module access
- [x] ระบุ Retail เป็น owner ของ operational records หลัง cutover โดยไม่รวม Table/Kitchen/Pickup

## WP7-B — Company workspace, staff และ device alignment

- [x] ใช้ Company Workspace provisioning เดิมสร้าง Retail Brand/Branch โดยไม่รับ database จาก client
- [x] ใช้ signed staff context และ `pos.*` permission compatibility เดิม
- [x] รองรับ Retail Counter pairing จาก Platform Device Registry
- [x] ปฏิเสธ Kitchen/Pickup device สำหรับ Retail และตรวจ Company `retail_pos` entitlement ก่อน pair/renew/use

## WP7-C — Retail database boundary และ operations

- [x] เพิ่ม `RETAIL_DATABASE_URL` และ server-owned `RETAIL_SERVICE_DATABASE=legacy|retail`
- [x] เพิ่ม physical `retail_ops_db`, Alembic chain `p7retail0001` และ boundary metadata `retail:1`
- [x] เพิ่ม Retail ใน migration, health, backup และ isolated restore tooling
- [x] route Product, Stock, Stock Count, POS และ Retail reports ผ่าน operational factory เดียวกัน
- [x] คงค่า default เป็น `legacy`; client และ token เลือก database เองไม่ได้

## WP7-D — Fail-closed gate และ rollout safety

- [x] Retail cutover ต้องใช้ Platform identity, reference projector, URL ชัดเจน และฐานจริงคนละชื่อ
- [x] startup ตรวจ operational table manifest ก่อนรับ traffic
- [x] schema contract version `1` ใน WP7 เป็น standby เท่านั้น; cutover ต้องเป็นอย่างน้อย version `2`
- [x] ไม่มีการเปิด WP5/WP6 write flags, deploy UAT/Production หรือย้ายข้อมูลจริง
- [x] automated full regression และ frontend build
- [ ] physical Retail scanner/printer/offline UAT (พักตามคำสั่ง owner)

## In scope / database

- `platform_core`: Retail module entitlement, Company/Brand/Branch/User/Device context เดิม
- `retail`: database identity, migration history และ backup/restore standby boundary
- `legacy`: Retail operational system of record เดิมระหว่าง compatibility period
- backend operational routing และ fail-closed startup validation
- เอกสาร ownership, cutover prerequisites และ rollback

## Out of scope

- ไม่ copy, delete, rename หรือย้ายข้อมูล Retail จริงใน WP7
- ไม่สลับ `RETAIL_SERVICE_DATABASE=retail` ใน UAT/Production
- ไม่ redesign หน้า Retail POS และไม่รวม SaleOrder กับ DiningOrder/TakeawayOrder
- ไม่เพิ่ม Table, Dining Session, Kitchen Ticket หรือ Pickup Queue ให้ Retail
- ไม่ query Restaurant/Takeaway operational database จาก Retail
- ไม่เปิด WP5/WP6 หรือ deploy/migrate UAT/Production

## Acceptance criteria

- [x] Retail Brand/Branch ใช้ Company Workspace และ signed context มาตรฐาน
- [x] Retail device ใช้ Counter เท่านั้นและถูกผูก Company/Brand/Branch
- [x] Retail operational routers เลือกฐานจาก server config เท่านั้น
- [x] ฐาน Retail มี migration/backup/restore แยกและ downgrade ได้
- [x] การสลับก่อน schema/data พร้อมถูกปฏิเสธตั้งแต่ startup
- [x] backend/full frontend automated gate ผ่าน
- [x] runtime ปกติยังเป็น Legacy และไม่มี UAT/Production activation

## Rollback

1. คงหรือคืน `RETAIL_SERVICE_DATABASE=legacy`
2. ถอด Retail URL ออกจาก runtime ได้โดย POS เดิมยังใช้ Legacy
3. revert routing/device/config ของ WP7 กลับ baseline WP6
4. downgrade Retail `p7retail0001 → base` หรือลบฐาน standby เฉพาะเมื่อยืนยันว่าไม่มีข้อมูลจริง
5. backup/restore ของ Platform, Restaurant และ Takeaway เดิมยังใช้ได้ โดย manifest ใหม่เพิ่ม Retail อีกหนึ่งไฟล์

รายละเอียด ownership และขั้น WP8 อยู่ที่ `docs/architecture/retail-pos-boundary.md`
หลักฐานตรวจรับอยู่ที่ `docs/scopes/WP7-PHASE-GATE-02.md`
