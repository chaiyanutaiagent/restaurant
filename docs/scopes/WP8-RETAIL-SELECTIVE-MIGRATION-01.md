# WP8-RETAIL-SELECTIVE-MIGRATION-01 — Retail Selective Data Migration and Canary

วันที่อนุมัติและเริ่มทำ: 2026-09-15

สถานะ: **uat_dark_launch — deploy commit `df12dcc` และสร้าง Retail v2 จริงใน UAT แล้ว;
Retail routing ยังอยู่ Legacy เพราะ UAT ไม่มี Retail Brand/ข้อมูล Retail ให้ย้าย; Production ยังไม่เปิด**

Baseline rollback: WP7 commit `bc4a93eb773dca924bddee0bac2146ef5156c8ee`

## เป้าหมาย

ย้ายเฉพาะข้อมูลปฏิบัติการของ Retail Company/Brand/Branch ที่ operator ระบุจาก Legacy ไป
`retail_ops_db` โดยไม่ clone ทั้งฐาน ไม่ย้าย Restaurant/Takeaway และสามารถตรวจ count/digest,
ทำซ้ำ และถอย routing กลับ Legacy ได้

## WP8-A — Table/FK/source ownership inventory

| กลุ่ม | ตารางใน Retail v2 | Source ก่อน cutover | Owner หลัง cutover | ขอบเขต/FK สำคัญ |
| --- | --- | --- | --- | --- |
| Reference projection | `companies`, `branches`, `brands`, `brand_branches`, `users` | Platform | Platform; Retail เป็น read-only projection | Company → Branch/Brand/User; BrandBranch → Brand/Branch/Store Location |
| Catalog | `units`, `categories`, `products`, `product_variants`, `product_images` | Legacy Retail slice | Retail | Category parent ต้องมาก่อน child; Product ต้องอยู่ใน Retail Brand ที่เลือก |
| Price | `price_lists`, `price_list_items` | Legacy Retail slice | Retail | item อ้าง PriceList/Product/Variant ใน slice เดียวกัน |
| Configuration | `branch_settings` | Legacy Retail slice | Retail | จำกัด Retail Branch ที่เลือก; default price list เป็น scalar reference |
| Stock | `stock_locations`, `stock_balances`, `stock_movements` | Legacy Retail slice | Retail | Company/Branch/Location/Product/Variant ต้องอยู่ใน source set เดียวกัน |
| Stock count | `stock_count_sessions`, `stock_count_items` | Legacy Retail slice | Retail | Session มาก่อน Item; User เป็น Platform projection |
| Sale | `cashier_shifts`, `sale_orders`, `sale_order_items`, `payments` | Legacy Retail slice | Retail | Shift มาก่อน Order; Order มาก่อน Payment/Item; refund payment parent มาก่อน child |
| Control/audit | `approval_grant_usages`, `audit_logs` | Legacy Retail slice | Retail | เก็บ evidence ของ Retail operation; ไม่มี cross-database FK |
| Integration | `operational_outbox_events` | Legacy Retail slice แล้วเขียนต่อใน Retail | Retail | ส่ง idempotent event ไป shared reporting; ไม่ query Platform ใน request |
| Projection/migration ledger | `retail_reference_projection_receipts`, `retail_migration_runs` | สร้างใหม่ใน WP8 | Retail | digest/เวลา/status; ไม่มี credential หรือ payload ลูกค้า |

รายการที่ตั้งใจไม่ย้าย: Restaurant dining/table/recipe/kitchen, Takeaway queue/pickup,
CRM/loyalty, notification, accounting/e-tax, purchase/transfer, HR/payroll และข้อมูล Company อื่น
รายการ shared ERP รับผ่าน outbox/projection เท่านั้น ไม่ถูก SQL join ข้ามฐาน

## WP8-B — Retail schema v2 และ Platform reference projection

- [x] เพิ่ม Alembic `p8retail0002` และ `database_boundary_metadata = retail:2`
- [x] manifest operational 25 ตาราง พร้อม FK ภายใน Retail database เท่านั้น
- [x] เพิ่ม projection receipt แยกจาก Restaurant projector
- [x] project Company/Branch/Retail Brand/BrandBranch/User แบบ idempotent
- [x] Retail `users.hashed_password` ใช้ sentinel ที่ login ไม่ได้และไม่อ่าน credential hash จาก Platform
- [x] startup cutover ตรวจ Platform identity, projectors, database names, schema และ reference parity แบบ fail closed

## WP8-C — Selective migration, replay และ reconciliation

- [x] operator ต้องเลือก `company_id` และ `brand_id` อย่างชัดเจน หรือใช้ all-retail พร้อม confirmation
- [x] server ตรวจ `business_type=retail_pos` และขยาย Branch จาก Platform BrandBranch
- [x] ปฏิเสธ Branch ที่ผูก Brand นอก migration scope เพราะ Sale/Audit เดิมไม่มี Brand FK ที่แยกได้แน่นอน
- [x] เลือก Product ด้วย Retail Brand; dependency Unit/Category ancestor/Variant/Image/Price ถูกดึงตาม FK
- [x] เลือก Location/Stock/Count/Shift/Sale/Payment/Audit/Outbox เฉพาะ Branch/Product source set
- [x] copy แบบ upsert ด้วย immutable id และเรียง self-FK parent ก่อน child
- [x] ตรวจ row count และ canonical SHA-256 digest รายตาราง
- [x] replay รอบสองได้ผล exact เหมือนเดิมและเก็บ migration run แบบ sanitized
- [x] ปฏิเสธ source ที่ไม่มี Retail Product/Location หรือมี operational reference หลุด Brand scope

คำสั่ง operator อยู่ที่ `app.utils.project_retail_references` และ
`app.utils.migrate_retail_data`; ค่า default ไม่ย้ายทุก tenant โดยอัตโนมัติ

## WP8-D — Local canary และ rollback

- [x] isolated PostgreSQL สร้าง Legacy/Platform/Restaurant/Retail boundaries ใหม่
- [x] Retail migration downgrade `v2 → v1` และ re-upgrade `v1 → v2`
- [x] backup Legacy/Platform/Retail ก่อน synthetic canary พร้อม SHA-256
- [x] synthetic Retail fixture: barcode → shift → sale/retry → refund → void → stock → net report → close shift
- [x] Retail writes อยู่ Retail DB; Legacy source stock และ sale history ไม่เปลี่ยน
- [x] Retail outbox ส่ง shared ERP facts แยก `module_key=retail_pos` และยอดสุทธิ reconcile
- [x] read-only rollback route ด้วย `RETAIL_SERVICE_DATABASE=legacy`
- [x] UAT deploy commit `df12dcc`, แยกฐาน Platform/Restaurant/Retail/Takeaway และเปิด Platform identity
- [x] UAT backup ก่อน/หลัง cutover, migration heads, reference parity, public health และ auto-login ผ่าน
- [ ] physical scanner/printer/cash drawer/offline UAT (พักตามคำสั่ง owner)
- [ ] ย้าย Retail tenant จริง, เปลี่ยน `RETAIL_SERVICE_DATABASE=retail` และ owner sign-off
- [ ] Production activation

## Security decisions

- Client/token เลือก physical database ไม่ได้; server map signed `target_database=retail_pos`
- Reference projector ตรวจ Retail boundary identity/schema v2 และชื่อฐานต้องแยกจาก Platform ก่อนเขียน
- Retail database ไม่มี authentication secret ที่ใช้งานได้; login/session/device authority อยู่ Platform
- Retail runtime ไม่เรียก legacy CRM/notification/accounting tables ใน transaction แต่ยังเขียน operational
  outbox เพื่อส่ง shared ERP แบบ async
- ไม่มี SQL foreign key, distributed transaction หรือ request-time join ข้าม database
- รายงาน operational ใช้ยอดสุทธิ `total_amount - refund_amount`; จำนวนเอกสารยังรวม refunded เพื่อ audit

## Rollback

1. หยุด Retail writes แล้วตั้ง `RETAIL_SERVICE_DATABASE=legacy`
2. restart และตรวจ login/barcode/read-only flow จาก Legacy
3. เก็บ Retail dump/outbox ไว้เพื่อ reconcile; ห้ามลบฐานหลังมี canary/production data
4. ถ้าจะลองใหม่ ให้ project references และ replay selective migration แล้วตรวจทุก digest ก่อน switch
5. revert WP8 source กลับ baseline WP7 ได้โดย Legacy ยังคงเป็น system of record

หลักฐานตรวจรับอยู่ที่ `docs/scopes/WP8-PHASE-GATE-02.md`
และหลักฐาน UAT จริงอยู่ที่ `docs/scopes/WP8-UAT-DARK-LAUNCH-03.md`
