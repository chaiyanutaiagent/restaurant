# Foodchainservice UX/UI Handoff — Desktop + Tablet

วันที่: `2026-09-18`
ผู้รับ: Product/UX/UI Designer
สถานะระบบ: workflow และ API มีอยู่แล้ว; งานออกแบบทำคู่ขนานกับ production hardening

## 1. Product model

Foodchainservice เป็น Multi-business SaaS หนึ่ง Company ใช้ Shared ERP ร่วมกันและเปิดได้หลาย workspace:

1. Company Admin
2. Shared ERP
3. Restaurant POS
4. Retail POS
5. Takeaway POS
6. Central Kitchen / Supply Chain

Platform Console เป็นพื้นที่ภายในของ Foodchainservice สำหรับดูแลลูกค้า แพ็กเกจ ระบบ และ Audit.
Hotel PMS และ native mobile app ไม่อยู่ในรอบนี้

## 2. Target devices

| Device | Primary use |
| --- | --- |
| Desktop `1440×900` ขึ้นไป | Platform, Admin, ERP, accounting, purchasing, reports, central operations |
| Tablet landscape `1024×768` | Restaurant/Retail/Takeaway POS, table, KDS, pickup, stock receiving |
| Tablet portrait | secondary support; ห้ามเป็น layout หลักของ POS |

Mobile phone web เป็น public customer QR/status เท่านั้น ไม่ใช่ employee workspace ใน scope นี้

## 3. Personas and permissions

- Foodchainservice Platform Owner
- Company Owner / Company Admin
- Brand Manager
- Branch Manager
- Cashier / Counter staff
- Purchaser
- Accountant
- Stock operator
- Central production operator
- Kitchen / KDS operator
- Pickup operator

ทุกแบบต้องแสดงเฉพาะ action ที่ role/scope ทำได้. ห้ามออกแบบ flow ที่อาศัยการซ่อนปุ่มอย่างเดียว;
server permission และ Company/Brand/Branch/Station context เป็น source of truth

## 4. Critical journeys

### Company onboarding

สมัคร → ยืนยันข้อมูล → Company Admin → เลือกโมดูล → สร้าง Brand/Branch → เชิญพนักงาน → จับคู่อุปกรณ์

### Restaurant

เปิดกะ → เลือกขายหน้าร้าน/เปิดโต๊ะ/รับกลับ → เพิ่มสินค้า/ตัวเลือก → ส่งครัว → KDS → พร้อมเสิร์ฟ/รับสินค้า
→ ชำระเงิน → ใบเสร็จ → ปิดกะ

ลูกค้า: สแกน session QR → สั่งอาหาร → ร้านยืนยัน → ติดตามสถานะ → ชำระ/ขอเช็กบิล

### Retail

เปิดกะ → ยิง barcode/ค้นหา → ปรับจำนวน/ส่วนลด → ลูกค้า/ภาษี → รับชำระ → พิมพ์ใบเสร็จ → คืน/ยกเลิกตามสิทธิ์

### Takeaway

รับเงินก่อน → ออกคิว → KDS → Pickup → ส่งมอบ พร้อม offline/retry ที่ไม่สร้างออเดอร์ซ้ำ

### Central Kitchen / Distribution

Demand หลาย Brand → วางแผนผลิต → จ่ายวัตถุดิบ Lot → บันทึก yield/waste → รับ Finished Goods
→ จัดส่งสาขา → สาขารับจริง/ส่วนต่าง → reconcile stock/cost

### Shared ERP

สินค้า/หน่วย → Supplier/PO → รับของ/Lot → AP/Payment/WHT → VAT ledger → ปิดงวด → รายงานแยก module/รวม Company

## 5. Navigation principles

- ชั้นแรกเลือก workspace; ไม่รวมทุกเมนูใน sidebar เดียว
- แสดง Company, Brand, Branch, Station และ online/offline status ในตำแหน่งคงที่
- POS ใช้ action-first navigation; ERP ใช้ task/domain navigation
- เปลี่ยน workspace แล้วต้องเห็น context และ permission ก่อนเริ่มงาน
- destructive/financial/stock actions ต้องมี confirmation, reason และผลหลังบันทึก

## 6. Required component states

ทุก component/หน้า critical ต้องออกแบบอย่างน้อย:

- loading/skeleton
- empty พร้อม next action
- validation error
- API/permission error
- offline, queued, syncing, synced, conflict
- disabled พร้อมเหตุผล
- success พร้อมเลขอ้างอิง
- partial/void/refund/reversal
- printer/scanner/camera unavailable

Touch target ขั้นต่ำ `44×44px`; POS primary action แนะนำ `48–56px`. ต้องรองรับ keyboard และ barcode input
โดย focus ไม่หายเมื่อสแกนต่อเนื่อง

## 7. Visual deliverables

1. Sitemap/IA ของ Platform, Company Admin และ 5 operational workspaces
2. Role journey และ task priority
3. Design tokens: color, typography, spacing, radius, elevation, status semantics
4. Desktop + tablet component library
5. High-fidelity prototype ของ critical journeys ในหัวข้อ 4
6. Responsive specification และ overflow/scroll ownership
7. Empty/error/offline/device states
8. Usability findings พร้อม severity และ recommendation
9. Developer handoff ที่มี component/state names ตรงกัน

## 8. Constraints that must not change silently

- session-scoped table QR; ห้ามกลับไปใช้ QR โต๊ะแบบถาวรที่เปิด order ได้ไม่จำกัด
- paid-first Takeaway และ idempotent offline queue
- Restaurant, Retail และ Takeaway แยก operational context/report แต่ส่ง Shared ERP contract เดียวกัน
- Central Kitchen วัตถุดิบร่วมได้ แต่ finished goods/recipe/cost ต้อง trace Brand ได้
- accounting/tax action ต้อง audit และ lock/reopen ตามสิทธิ์
- Platform Owner แยก identity จาก tenant staff และห้าม impersonate แบบเงียบ

## 9. Review checkpoints

- Review A: IA + role journeys
- Review B: low-fidelity critical flows
- Review C: design system + high-fidelity POS/ERP
- Review D: clickable prototype usability test
- Review E: implementation visual QA บน desktop/tablet

ไฟล์ออกแบบยังไม่ถือว่าอนุมัติจน Product Owner ระบุ decision และวันที่ใน review record
