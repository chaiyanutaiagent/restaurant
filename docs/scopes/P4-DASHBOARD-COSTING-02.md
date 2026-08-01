# Scope ID: P4-DASHBOARD-COSTING-02

สถานะ: **Verified — dashboard reconciliation and auditable recipe costing complete**

Phase: **Phase 4 — Restaurant ERP Core**

Business type: **restaurant**

Target database: **Restaurant operational database ผ่าน `get_restaurant_service_db`; legacy runtime remains the rollback-safe default until cutover**

## Problem

Brand report มีข้อมูลยอดขาย สต็อก สูตร และครัวกลางแล้ว แต่ยังไม่มี reconciliation contract ที่ยืนยันว่า
ยอดรวมเท่ากับผลรวมรายการต้นทาง และ recipe costing คืนเพียงตัวเลขต้นทุนโดยไม่บอกแหล่งราคา/หน่วยที่ใช้
นอกจากนี้ unit conversion เดิมยอมรับหน่วยว่าง ไม่รู้จัก หรือคนละมิติแบบเงียบ ๆ ทำให้ต้นทุนต่อจานดูถูกต้อง
ทั้งที่ตรวจสอบย้อนกลับไม่ได้

## In Scope

- บังคับ ingredient quantity/unit ให้แปลงไปยังหน่วยสต็อกของวัตถุดิบได้ก่อน create/update recipe
- คืน cost provenance ต่อ ingredient: source, source reference, cost unit, normalized quantity และ conversion factor
- เพิ่ม Brand operations dashboard totals สำหรับยอดขาย ต้นทุนสูตร ของเสีย และการปิดกะ
- เพิ่ม reconciliation block เปรียบเทียบ Brand aggregate กับ source order/payment/branch rows พร้อม delta
- ใช้ Asia/Bangkok business date อย่างสม่ำเสมอ
- รักษา Company/Brand/Branch authorization จาก `P4-REPORT-SCOPE-01`
- เพิ่ม unit/API regression ที่พิสูจน์ compatible conversion, incompatible rejection และ aggregate equality

## Out of Scope

- AI forecast, advanced CRM และ franchise royalty
- การเปลี่ยน accounting handoff หรือ outbox ซึ่งอยู่ `P4-SALE-HANDOFF-03`
- Takeaway/Retail report หรือ operational database
- production feature flag และ employee assignment ซึ่งอยู่ Scope ถัดไป
- production runtime cutover

## Database / Ownership

- Recipe, Product, PurchaseOrderItem, SaleOrder, Payment, StockMovement และ shift closure เป็น Restaurant operational records
- Endpoint ต้องใช้ immutable `company_id`, `brand_id`, `branch_id` จาก server-owned context
- ไม่มี SQL join/FK ไป Retail หรือ Takeaway database
- Scope นี้ไม่เพิ่มตารางและไม่เขียน live database

## Acceptance

- [x] `kg -> g`, `l -> ml` และ alias ภาษาไทยคำนวณด้วย factor ที่แสดงใน response
- [x] หน่วยว่าง ไม่รู้จัก หรือคนละมิติถูกปฏิเสธก่อนบันทึก recipe
- [x] ต้นทุนแต่ละ ingredient ระบุ purchase receipt หรือ product fallback ที่ใช้
- [x] Brand aggregate sales เท่ากับผลรวม source order และ branch rows ภายใน 0.01 บาท
- [x] Payment reconciliation แสดง delta จากยอดขายและสถานะผ่าน/ไม่ผ่าน
- [x] Dashboard แสดง recipe cost และ waste cost จาก Restaurant source rows
- [x] Company/Brand/Branch authorization regression ผ่าน

## Execution Record

- Unit conversion/costing และ reconciliation regression รวมอยู่ใน backend 174 tests
- Brand report API matrix ผ่าน Company, Brand, Branch และ shift scope
- Recipe/inventory smoke ผ่าน strict stock-unit validation และ automatic unit linking
- Frontend type-check และ production/PWA build ผ่าน; มี chunk-size warning เดิม
- หลักฐานรวมอยู่ใน `P4-PHASE-GATE-06`

## Rollback

- Revert code/schema response additions; ไม่มี destructive data migration
- Response fields ใหม่เป็น additive เพื่อให้ client เก่ายังทำงาน
- Legacy runtime default และ live database ไม่เปลี่ยน
