# Retail POS Database Boundary

สถานะ: WP8 local cutover-ready / Retail operational runtime จริงยังเป็น Legacy

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

WP7 เปลี่ยน routers เหล่านี้ให้ใช้ server-owned operational factory เส้นเดียวกัน และ WP8 เพิ่ม schema
contract v2, Platform reference projection, selective copy/reconciliation, shared reporting source และ
local canary/rollback แล้ว ค่า runtime จริงยังคง `RETAIL_SERVICE_DATABASE=legacy` จึงยังไม่เปลี่ยน
ข้อมูลหรือพฤติกรรมผู้ใช้เดิมใน UAT/Production

## Runtime modes

| ค่า | พฤติกรรม |
| --- | --- |
| `RETAIL_SERVICE_DATABASE=legacy` | Retail POS เดิมทำงานต่อบน Legacy; เป็นค่า default และ rollback |
| `RETAIL_SERVICE_DATABASE=retail` | อนุญาตเฉพาะเมื่อใช้ Platform identity/projectors, URL ชัดเจน, database คนละชื่อ, manifest table ครบ, contract version ≥ 2 และ reference parity exact |

WP8 ยก local Retail schema เป็น `database_boundary_metadata = retail:2` และ startup ยังคง fail closed
หาก reference projection ไม่ครบหรือ digest ไม่ตรง การมี schema v2 เพียงอย่างเดียวไม่ถือว่าอนุญาตให้
เปิด UAT/Production

## Operational manifest ใน WP8

อย่างน้อยต้องมีและผ่าน parity ก่อนยก contract เป็น version 2:

- references: `companies`, `brands`, `branches`, `brand_branches`, `users`
- catalog: `units`, `categories`, `products`, `product_variants`, `product_images`
- pricing: `price_lists`, `price_list_items`
- stock: `stock_locations`, `stock_balances`, `stock_movements`
- stock count: `stock_count_sessions`, `stock_count_items`
- sale: `cashier_shifts`, `sale_orders`, `sale_order_items`, `payments`
- controls/integration: `branch_settings`, `approval_grant_usages`, `audit_logs`, `operational_outbox_events`
- ledgers: `retail_reference_projection_receipts`, `retail_migration_runs`

CRM, loyalty, notification, accounting, e-tax, purchase, transfer, HR, Restaurant และ Takeaway tables
ไม่อยู่ใน Retail v2 รายการ shared ERP ใช้ outbox/projection เท่านั้น ห้าม clone ทั้ง Legacy แล้วเปิดใช้
เพราะอาจพา Restaurant หรือ Company อื่นเข้าฐาน Retail

## Device

Retail รองรับ `counter` เท่านั้นใน WP7 อุปกรณ์ถูกสร้างและ pair ผ่าน Platform Device Registry พร้อม
signed Company/Brand/Branch/`retail_pos` context และ Company entitlement ส่วน Kitchen/Pickup เป็น
capability ของ Restaurant/Takeaway จึงถูกปฏิเสธ

## Cutover sequence หลัง WP8 local gate

1. ระบุ Retail Company/Brand/Branch จริงและ freeze write window
2. backup Legacy/Platform/Retail แล้ว project Platform references ให้ parity exact
3. selective copy, replay และ reconcile count/digest/amount/stock
4. ทดสอบ Product → Scan → Shift → Sale → Payment → Receipt → Refund/Void → Stock → Report
5. ทำ physical scanner/printer/cash drawer/offline UAT
6. owner sign-off ก่อน UAT/Production switch; rollback คือ `RETAIL_SERVICE_DATABASE=legacy`

รายละเอียด table ownership, tooling และ local evidence อยู่ที่
`docs/scopes/WP8-RETAIL-SELECTIVE-MIGRATION-01.md`
