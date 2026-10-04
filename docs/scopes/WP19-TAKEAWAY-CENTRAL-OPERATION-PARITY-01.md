# WP19 — Takeaway Central Operation Parity

วันที่: 2026-09-17

สถานะ: **completed — โค้ดและ local migration ผ่าน; ยังไม่เปิด UAT/Production**

## ผลลัพธ์

- สูตรผลิตแบบ versioned พร้อม effective date, yield, loss, nested-recipe cycle guard และต้นทุนต่อผลผลิต
- Replenishment policy รายสาขา พร้อม safety stock, pack size, lead time, minimum order, คำแนะนำจากยอดขาย/คงเหลือ/ของระหว่างทาง และสร้างใบสั่งอัตโนมัติ
- ใบสั่งส่วนกลางรองรับ resolve สินค้านอก catalog, จำนวนอนุมัติ/แพ็ก/ส่ง/รับจริง, รับบางส่วน และ discrepancy resolution
- การผลิตรองรับ planned → in progress → completed/cancelled, actual quantity, waste และ stock ledger แบบ idempotent
- Transfer รองรับจำนวนส่ง/รับจริง, partial receive และ discrepancy resolution
- เครดิตรองรับ ledger, payment QR/bank config, top-up request, approve/reject และ ERP outbox
- Operational control tower รวมยอดขาย ใบสั่ง การผลิต transfer เครดิต discrepancy และ ERP backlog
- หน้า `/takeaway/central/recipes` ใช้งานจริงสำหรับสูตรและ replenishment policy
- ทุก workflow ใหม่ตรวจ company/brand/branch จาก signed context และออก ERP event แบบ versioned

## Database

- Migration: `p6takeaway0006`
- เพิ่มเฉพาะตาราง/คอลัมน์ใน Takeaway database
- ไม่ join หรือเขียน Restaurant/Retail database โดยตรง

## หลักฐานตรวจ

- Takeaway focused tests: 16 ผ่าน
- Backend regression: 373 ผ่าน, skipped 1
- Frontend type-check: ผ่าน
- Frontend production build: 4,221 modules ผ่าน
- Local Takeaway migration: `p6takeaway0005 → p6takeaway0006` ผ่าน

## สิ่งที่ยังไม่ถือว่าผ่านจาก WP นี้

- เครื่องพิมพ์ Bluetooth และ Android signed release เป็น WP20
- ข้อมูล Chambo จริงและ cutover tool เป็น WP21/WP25
- Physical device UAT และ Production activation เป็น WP24/WP26
