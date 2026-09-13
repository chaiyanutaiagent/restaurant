# Shared ERP Reporting Boundary

สถานะ: WP4 local implementation; Shadow/read-only และยังไม่เปิด UAT/Production

## Ownership matrix

| ข้อมูล | System of record ระหว่าง cutover | ผู้เขียน | รายงานกลางใช้แบบใด |
| --- | --- | --- | --- |
| Company, Brand, Branch, BrandBranch | Platform core เมื่อ identity cutover; legacy ก่อน cutover | Company/Platform services | ใช้เป็น dimension ที่ server ตรวจ Company และ active workspace |
| ERP product, supplier, accounting master | Legacy ERP จนมี work package ย้ายเฉพาะทาง | ERP services | ไม่คัดลอกใน WP4 |
| Restaurant sale, payment, refund, void | Legacy หรือ Restaurant operational DB ตาม runtime route | Restaurant/POS service | อ่าน outbox allow-list และ snapshot เอกสารต้นทาง |
| Takeaway order, payment, refund | Takeaway operational DB | Takeaway service | อ่าน Takeaway outbox allow-list และ snapshot เอกสารต้นทาง |
| Retail sale, payment, refund, void | Legacy/Retail compatibility boundary | Retail POS service | อ่าน operational outbox allow-list และ snapshot เอกสารต้นทาง |
| Company reporting fact/receipt/cursor | Platform core | Shared reporting projector เท่านั้น | derived, rebuildable, PII-free, ไม่ใช่ ledger ต้นทาง |
| Central Kitchen stock/production | Restaurant boundary ชั่วคราว | Central Kitchen services เดิม | ไม่ย้ายและไม่ตัดสต๊อกข้ามแบรนด์ใน WP4 |
| Hotel | ยังไม่มี schema | ไม่มี | planned; ไม่นับเป็นโมดูลที่เปิดใช้งาน |

ตารางหนึ่งมี owner เพียง boundary เดียว การฉายข้อมูลไม่ได้เปลี่ยนเจ้าของเอกสารต้นทาง และ projector
ไม่เปิด transaction หรือ join ข้าม database: อ่าน source ทีละฐาน แล้ว commit derived fact ใน Platform แยกกัน

## Stable dimensions และเวลา

ทุก `CompanyReportingFact` ต้องมี:

- `company_id` จาก source event และต้องตรงกับ Platform Brand/Branch
- `module_key`: `restaurant_pos`, `takeaway_pos` หรือ `retail_pos`
- `business_type`: `restaurant`, `takeaway` หรือ `retail_pos` และต้อง map กับ module แบบตายตัว
- `brand_id`, `branch_id` และ active BrandBranch ที่อยู่ Company เดียวกัน
- `business_date` ของ source โดย Restaurant/Retail แปลงเวลาสร้างเป็น `Asia/Bangkok`; Takeaway ใช้ business date ที่ source บันทึก
- `source_document_type`, `source_document_id`, `source_stream`, `last_source_event_id`

Client ส่งได้เฉพาะช่วงวันที่และตัวกรอง module/Brand/Branch สำหรับการอ่าน Company ของตัวเอง ห้ามส่ง Company
เป้าหมาย, ชื่อ database หรือ dimension สำหรับการเขียน

## Event, replay และ reversal

Allow-list ปัจจุบัน:

| Source | Event |
| --- | --- |
| Restaurant/Retail | `restaurant.sale.completed.v1`, `pos.sale.state.changed.v1` |
| Takeaway | `takeaway.sale.paid.v1`, `takeaway.sale.refunded.v1` |

- receipt unique ด้วย `(source_stream, source_event_id)` และเก็บเฉพาะ SHA-256 ของ payload ไม่คัดลอก PII
- fact unique ด้วย Company/module/source document; event ที่ใหม่กว่าแก้ snapshot เดิม ส่วน event เก่าถูกลง receipt แต่ไม่ย้อนยอด
- partial refund, full refund และ void เป็น source state ที่ตรวจสอบย้อนกลับได้ ไม่แก้ aggregate แบบไร้ event
- projector มี cursor แยกจาก consumer อื่น จึงไม่แย่ง `processed_at` ของ outbox เดิม
- ความผิดพลาด retry 5 ครั้งก่อน dead-letter; UI แสดง degraded/stale และไม่อ้างว่าเป็นข้อมูลล่าสุด

## Read contract และ rollout

- `GET /api/v1/membership/reports/shared-sales` ต้องมี `system.company.edit` หรือ wildcard
- API ยึด Company จาก signed token และจำกัดช่วงสูงสุด 93 วัน
- `/reports/company` แสดง totals, module, Brand/Branch และ source document route
- projection mode คงเป็น `shadow`, `is_source_of_truth=false`
- `SHARED_REPORTING_PROJECTOR_ENABLED=false` เป็นค่าเริ่มต้น
- การเปิด projector ต้องใช้ `IDENTITY_DATABASE=platform_core` และ `REFERENCE_PROJECTOR_ENABLED=true`
- ก่อนใช้ตัดสินใจจริง ต้องเทียบ source fixtures/รายงานต้นทางให้ต่างไม่เกิน `0.01 THB` ต่อ Company/module/day

การ rollback ให้ปิด UI/projector ก่อน ข้อมูลขายเดิมยังทำงานต่อได้ และตาราง projection สามารถลบ/rebuild จาก source
โดยไม่แก้ operational record
