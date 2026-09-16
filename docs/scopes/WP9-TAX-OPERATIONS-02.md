# WP9-TAX-OPERATIONS-02 — Shared ERP Tax Operations (B–H)

สถานะ: **UAT deployed / ยังไม่ deploy Production / รอ physical UAT และ accountant review**
วันที่: 16 กันยายน 2026
Owner approval: Approved — ผู้ใช้สั่ง “ทำต่อ B-H”

## 1. Outcome

เพิ่มศูนย์ภาษีกลางของ Foodchainservice ที่รวมยอดจาก Restaurant POS, Retail POS, Takeaway POS และ
Purchasing/AP โดยคงฐานข้อมูลปฏิบัติการของแต่ละโมดูลแยกจากกัน ระบบทำทะเบียน ตรวจหลักฐาน ล็อกงวด
และสร้างชุดข้อมูลให้ผู้ทำบัญชีได้ แต่ **ยังไม่ยื่นแบบหรือส่งข้อมูลไปกรมสรรพากรอัตโนมัติ**

## 2. Work Packages B–H

| งาน | สิ่งที่ทำแล้ว |
|---|---|
| WP9-B Output VAT | ทะเบียนภาษีขาย แยก Company/Branch/Brand/Module รองรับ refund/void และ idempotent source key |
| WP9-C Input VAT | ใบซื้อเก็บเลข/วันที่ใบกำกับ สิทธิ์ภาษีซื้อ เหตุผลไม่ใช้สิทธิ์ และตรวจหลักฐานผู้ขาย |
| WP9-D WHT | จำแนกผู้ขายบุคคลธรรมดา/นิติบุคคล และสร้างข้อมูล ภ.ง.ด.3/53 จากใบรับรอง AP |
| WP9-E e-Tax reconciliation | เทียบยอดขายกับเอกสาร e-Tax ตรวจเอกสารหาย ยกเลิก หรือยอดไม่ตรง |
| WP9-F Period close | Open → Review → Closed, ล็อกการแก้ย้อนหลัง, เปิดงวดใหม่พร้อมเหตุผลและผู้ทำรายการ |
| WP9-G Export | VAT sales/purchases, ภ.พ.30 summary, ภ.ง.ด.3/53, e-Tax manifest และ archive manifest พร้อม SHA-256 |
| WP9-H Readiness | ตรวจ Tax Profile, branch, หลักฐานซื้อ, WHT classification, e-Tax และ blocker ก่อนปิดงวด |

## 3. Database Boundary

- System of record ของ Tax Operations: **Shared ERP / legacy operational database**
- Legacy Restaurant/Retail data ใช้คำสั่ง sync แบบ idempotent จาก SaleOrder และ SupplierInvoice
- Retail/Takeaway ที่แยกฐานข้อมูลส่ง normalized tax event ผ่าน `POST /api/v1/tax-operations/ledger`
- ห้าม Shared ERP query ตาราง operational ของ Retail/Takeaway database โดยตรง
- unique source contract: Company + Module + document type + document id + line key + direction
- ปิดงวดแล้ว ingestion และ sync ของงวดนั้นถูกปฏิเสธจนกว่าจะเปิดงวดใหม่

## 4. Data Model

Migration `p16taxops0018` ต่อจาก `p15taxset0017`:

- `tax_ledger_entries`
- `tax_periods`
- `tax_reconciliation_issues`
- `tax_export_batches`
- เพิ่ม `suppliers.tax_entity_type`
- เพิ่ม `supplier_invoices.tax_invoice_number`, `tax_invoice_date`, `input_vat_claimable`, `nonclaimable_reason`

Migration เป็น additive และ downgrade ลบเฉพาะตาราง/คอลัมน์ของ WP นี้

## 5. API และ Permission

สิทธิ์ใหม่:

- `accounting.tax.view` — ดูศูนย์ภาษีและดาวน์โหลดไฟล์
- `accounting.tax.manage` — sync, reconcile, จัดการงวดและสร้างไฟล์
- Company Owner ได้สิทธิ์ทั้งสองโดยค่าเริ่มต้น
- รองรับ `accounting.report.view` สำหรับอ่าน และ `system.company.edit` สำหรับบริหาร เพื่อรักษา compatibility

| Method | Route | หน้าที่ |
|---|---|---|
| GET | `/api/v1/tax-operations/dashboard` | ภาพรวม ledger/issues/WHT/exports/readiness |
| POST | `/api/v1/tax-operations/sync/legacy` | นำข้อมูลขายและซื้อเดิมเข้าทะเบียนแบบไม่ซ้ำ |
| POST | `/api/v1/tax-operations/ledger` | normalized contract สำหรับ POS/ระบบภายนอก |
| POST | `/api/v1/tax-operations/reconcile` | ตรวจ e-Tax, ภาษีซื้อ, WHT และ Tax Profile |
| POST | `/api/v1/tax-operations/periods/{review,close,reopen}` | วงจรปิดงวด |
| PATCH | `/api/v1/tax-operations/issues/{id}` | ปิดหรือรับทราบข้อสังเกตพร้อมหมายเหตุ |
| POST | `/api/v1/tax-operations/exports` | สร้าง versioned export พร้อม hash |
| GET | `/api/v1/tax-operations/exports/{id}/download` | ดาวน์โหลดไฟล์ที่สร้างไว้ |

ทุก route ใช้ Company ID และ Actor ID จาก signed token ไม่รับ Company ID จาก client

## 6. Company Admin UI

หน้า `/tax-center` มี:

- เลือกปี/เดือนและดูสถานะงวด
- ภาษีขาย ภาษีซื้อ ภาษีสุทธิ และหัก ณ ที่จ่าย
- ทะเบียนภาษีแยก source module
- ผลตรวจ readiness และการแก้/รับทราบ issue
- ส่งตรวจ ปิดงวด เปิดงวดใหม่
- สร้างและดาวน์โหลดชุดข้อมูลภาษี
- แสดง SHA-256 สำหรับตรวจความครบถ้วนย้อนหลัง

## 7. Acceptance Criteria

- [x] Ledger source key idempotent และแยก Module/Branch/Brand
- [x] Refund/void ไม่สร้าง Output VAT ซ้ำ
- [x] ภาษีซื้อที่ใช้สิทธิ์แต่ไม่มีเลขใบกำกับถูกแจ้งเป็น error ก่อนปิดงวด โดยไม่ทำลาย legacy invoice flow
- [x] ใบซื้อไม่ใช้สิทธิ์ต้องมีเหตุผล
- [x] ภ.ง.ด.3/53 แยกจากประเภทผู้ขาย
- [x] e-Tax mismatch ถูกบันทึกเป็น issue
- [x] ปิดงวดไม่ได้เมื่อมี error/blocker หรือรายการรอกระทบยอด
- [x] งวดปิดแล้วแก้ ledger ไม่ได้จนกว่าจะ reopen พร้อมเหตุผล
- [x] Export ทุกไฟล์มี SHA-256 และประวัติ version
- [x] ไม่มี cross-database query/transaction
- [x] Migration จากฐานว่างถึง `p16taxops0018` ผ่าน
- [x] Focused backend tests ผ่าน
- [x] Frontend type-check ผ่าน
- [ ] Physical UAT / real accountant review — พักไว้ตามคำสั่ง owner
- [x] Deploy UAT พร้อม backup, migration และ API smoke
- [x] Functional UAT ด้วยข้อมูลจำลองครบ sync/reconcile/review/close/lock/reopen/export
- [ ] Deploy Production — ต้องผ่าน physical UAT และ owner sign-off ก่อน

## 8. Non-goals / Legal Boundary

- ไม่ยื่น ภ.พ.30, ภ.ง.ด.3 หรือ ภ.ง.ด.53 ให้กรมสรรพากรอัตโนมัติ
- ไม่ใช้ digital certificate/signature และไม่เชื่อม e-Tax Service Provider
- ไฟล์เป็น working package ให้ผู้ทำบัญชีตรวจและนำไปใช้ต่อ ไม่รับรองว่าเป็นรูปแบบ upload ของผู้ให้บริการรายใด
- ไม่ย้ายข้อมูลจริงข้าม database boundary และยังไม่เปิด feature บน Production

## 9. Rollback

1. หยุด Tax Center และ ingestion
2. เก็บ export/ledger snapshot และ backup ฐานข้อมูล
3. ถอย application image/commit
4. downgrade `p16taxops0018` → `p15taxset0017`
5. ระบบ POS, AP และ e-Tax เดิมยังทำงานต่อโดยไม่พึ่งตาราง Tax Operations

## 10. Verification

- Fresh database migration ถึง `p16taxops0018`: ผ่าน
- Migration rollback rehearsal `p16 → p15 → p16`: ผ่าน
- Focused backend tax/permission tests: `26` ผ่าน
- Backend full regression: `346` ผ่าน, skip `1`
- Frontend TypeScript: ผ่าน
- Frontend production PWA build: ผ่าน (`4,210` modules)
- `git diff --check`: ผ่าน

## 11. UAT Deployment Evidence

- Feature commit: `a08122a9a786b030b1103e34dba2c1d6022b6fb0`
- UAT audit snapshot fix: `74f3e928427c8a7ecf48f236c332b8e58cf2c276`
- UAT ignored-warning persistence fix: `2f9831b`
- UAT URL: `https://uat-pos.foodchainservice.com`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/a08122a9a786b030b1103e34dba2c1d6022b6fb0`
- Rollback backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/a08122a`
- Migration: `p14dist0016 → p15taxset0017 → p16taxops0018`
- Images: `restaurant-pos-backend:wp9-2f9831b`, `restaurant-pos-frontend:wp9-a08122a`,
  `restaurant-pos-nginx:wp9-a08122a`
- Internal/public live และ ready health: HTTP `200`
- UAT auto-login, `GET /api/v1/tax-settings` และ
  `GET /api/v1/tax-operations/dashboard?year=2026&month=9`: HTTP `200`
- Cloudflare Tunnel precheck ผ่าน และ Production ไม่ถูกเปลี่ยนแปลง
- Functional UAT ใช้ข้อมูลที่ระบุชัดว่าเป็นข้อมูลจำลอง: Restaurant/Retail/Takeaway output VAT และ
  Purchasing input VAT รวม 4 ledger rows; ฐานภาษีขาย `1,800.00`, ภาษีขาย `126.00`, ฐานภาษีซื้อ
  `400.00`, ภาษีซื้อ `28.00`, ภาษีสุทธิ `98.00`
- Reconcile เหลือ warning e-Tax จำลอง `3` รายการ, blocker `0`, pending `0`; ทดสอบปิดงวด,
  ปฏิเสธ ingestion ขณะปิดงวดด้วย HTTP `409`, เปิดงวดใหม่ และปล่อยสถานะสุดท้ายเป็น `open`
- สร้าง `pp30_summary_2026_09.csv` และตรวจ SHA-256 ตรงกัน
- Backup ก่อนข้อมูลจำลอง:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/a08122a/before-simulated-tax-data-20260916.dump`
- Backup ก่อน UAT รอบสอง:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/a08122a/before-tax-uat-round2-20260916.dump`
- UAT รอบสองสร้าง Sale Order จริงและ e-Tax invoice จริงใน UAT, ตรวจ XML/PDF HTTP `200`,
  ตั้ง Supplier Invoice และชำระเจ้าหนี้ `2` ราย (บุคคลธรรมดา/นิติบุคคล), สร้างหนังสือรับรอง
  หัก ณ ที่จ่าย ภ.ง.ด.3/53 อย่างละ `1` รายการ และตรวจ PDF ใบรับรอง/ใบสำคัญจ่าย HTTP `200`
- หลังเพิ่มข้อมูลรอบสองมี ledger `7` รายการ: ภาษีขายฐาน `1,864.49`, ภาษีขาย `130.51`,
  ภาษีซื้อฐาน `2,200.00`, ภาษีซื้อ `154.00`, ภาษีสุทธิ `-23.49` และหัก ณ ที่จ่าย `54.00`
- แก้ regression ที่ reconciliation เปิด warning ซึ่งถูก mark `ignored` กลับมาใหม่; focused tax/settings/role
  tests ผ่าน `29` รายการ และหลัง deploy กระทบยอดได้ blocker `0`, warning `0`, pending `0`
- ทดสอบ Review → Close, ปฏิเสธการเขียนงวดปิด HTTP `409`, export ครบ `7` ประเภทและตรวจ
  SHA-256 ตรงกันทุกไฟล์ จากนั้น Reopen และปล่อยสถานะสุดท้ายเป็น `open`
- Live role preset check ผ่านครบ `5` preset โดยไม่มี permission สูญหาย; Company Owner มีสิทธิ์สร้าง/แก้
  ผู้ใช้และ role รวมถึงสิทธิ์จัดซื้อ บัญชี และบริหารภาษี ส่วน role เฉพาะ Accountant/Purchasing
  ใช้ Custom Role ตาม permission ที่ต้องการ

## 12. งานถัดไป

Physical UAT กับเจ้าของระบบและผู้ทำบัญชี โดยใช้ข้อมูลจำลองก่อน แล้วจึงทำ Production deployment plan
แยกพร้อม backup, rehearsal, rollback และ owner sign-off ห้ามเปิด Production จากเอกสารนี้โดยอัตโนมัติ
