# Retail POS Database Boundary

สถานะ: WP7 local foundation / Retail operational runtime ยังเป็น Legacy

## Ownership หลัง target cutover

| ข้อมูล | System of record | หมายเหตุ |
| --- | --- | --- |
| Company, Brand, Branch, User, staff assignment, Device, module access | Platform core | Retail เก็บ scalar reference/projection เท่านั้น |
| Unit, Category, Product, Variant, SKU, Barcode, Price | Retail | ห้ามแชร์ Product table กับ Restaurant/Takeaway |
| Stock location, balance, movement, count | Retail | แยก Company/Brand/Branch/Location |
| Cashier shift, Sale, Sale item, Payment, Receipt, Refund/Void evidence | Retail | ใช้ Retail transaction เดียว |
| Shared ERP/reporting | Platform/shared read model | รับ idempotent event; ไม่ join Retail DB ใน request |
| Central Kitchen/Distribution | Legacy shared service ระหว่าง dark launch | เชื่อมด้วย demand/event contract ไม่อ่าน Retail DB โดยตรง |

## สภาพปัจจุบัน

Retail POS เดิมใช้ generic tables บน Legacy และ route `/products`, `/stock`, `/stock-count`, `/pos`
กับ `/reports` บางส่วน เดิมมี Company/Branch scope และ `pos.*` permissions อยู่แล้ว แต่ product/report
routers บางส่วนเปิด connection ตรงไป Legacy ทำให้ cutover เป็นรายโมดูลไม่ได้

WP7 เปลี่ยน routers เหล่านี้ให้ใช้ server-owned operational factory เส้นเดียวกัน ค่า default ยังคง
`RETAIL_SERVICE_DATABASE=legacy` จึงไม่เปลี่ยนข้อมูลหรือพฤติกรรมผู้ใช้เดิม

## Runtime modes

| ค่า | พฤติกรรม |
| --- | --- |
| `RETAIL_SERVICE_DATABASE=legacy` | Retail POS เดิมทำงานต่อบน Legacy; เป็นค่า default และ rollback |
| `RETAIL_SERVICE_DATABASE=retail` | อนุญาตเฉพาะเมื่อใช้ Platform identity/projector, URL ชัดเจน, database คนละชื่อ, manifest table ครบ และ contract version ≥ 2 |

ฐานที่สร้างใน WP7 มี `database_boundary_metadata = retail:1` เท่านั้น จึงเป็น standby และตั้งใจให้
startup ปฏิเสธ cutover แม้ operator ใส่ URL แล้ว ขั้นนี้ป้องกัน traffic เข้าฐานว่างหรือ snapshot ที่ยัง
ไม่มี reference projection ต่อเนื่อง

## Operational manifest สำหรับ WP8

อย่างน้อยต้องมีและผ่าน parity ก่อนยก contract เป็น version 2:

- references: `companies`, `brands`, `branches`, `brand_branches`, `users`
- catalog: `units`, `categories`, `products`, `product_variants`
- stock: `stock_locations`, `stock_balances`, `stock_movements`
- sale: `cashier_shifts`, `sale_orders`, `sale_order_items`, `payments`
- controls/integration: `branch_settings`, `approval_grant_usages`, `audit_logs`, `operational_outbox_events`

WP8 ต้องจำแนกตารางเสริม เช่น CRM, price list, image, accounting, e-tax, purchase, transfer และ
offline queue ว่าเป็น Retail-owned, shared ERP หรือ event projection ก่อน copy ห้าม clone ทั้ง Legacy
แล้วเปิดใช้ทันที เพราะอาจพา Restaurant/Company อื่นเข้าฐาน Retail

## Device

Retail รองรับ `counter` เท่านั้นใน WP7 อุปกรณ์ถูกสร้างและ pair ผ่าน Platform Device Registry พร้อม
signed Company/Brand/Branch/`retail_pos` context และ Company entitlement ส่วน Kitchen/Pickup เป็น
capability ของ Restaurant/Takeaway จึงถูกปฏิเสธ

## WP8 cutover sequence

1. ทำ table/FK inventory และกำหนด Retail tenant/Brand/Branch source set
2. สร้าง Retail schema version 2 โดยไม่มี cross-database foreign key
3. ทำ Platform reference projection สำหรับ Retail แบบ idempotent และมี consumer receipt แยก
4. snapshot เฉพาะ Retail, copy, reconcile counts/amount/stock และทดสอบ replay
5. ทดสอบ Product → Scan → Shift → Sale → Payment → Receipt → Refund/Void → Stock → Report
6. backup แล้วทำ local canary; physical scanner/printer/offline UAT
7. owner sign-off ก่อน UAT/Production switch; rollback คือ `RETAIL_SERVICE_DATABASE=legacy`
