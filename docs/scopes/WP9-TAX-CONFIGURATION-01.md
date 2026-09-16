# WP9-TAX-CONFIGURATION-01 — Shared ERP Tax Configuration

สถานะ: **UAT deployed / ยังไม่ deploy Production / รอ physical UAT**
วันที่: 16 กันยายน 2026
Owner approval: Approved — ผู้ใช้สั่ง “ทำ 1 ได้เลย” สำหรับงานลำดับ 1 (WP9-A)

## 1. Problem

ข้อมูลภาษีเดิมกระจายอยู่ใน Company, Product, POS, e-Tax และ AP โดยยังไม่มีจุดตั้งค่ากลางสำหรับ
ชื่อจดทะเบียน เลขผู้เสียภาษี สาขาตาม ภ.พ.20 รูปแบบยื่น ภ.พ.30 และอัตราภาษีตามช่วงเวลา อีกทั้ง
e-Tax ใช้รหัสสาขา `00000` แบบตายตัว จึงไม่เหมาะกับบริษัทหลายสาขาและ POS หลายประเภท

## 2. Ownership และ Database Boundary

- System of record: **Shared ERP / legacy operational database**
- Owner: Company Admin
- Consumers: Restaurant POS, Retail POS, Takeaway POS, Purchasing/AP และ e-Tax
- Permission แก้ไข: `system.company.edit`
- Permission อ่าน: `system.company.view`, `system.company.edit` หรือ `accounting.report.view`
- ไม่ทำสำเนา Tax Profile แยกลง Restaurant, Retail หรือ Takeaway database ใน WP นี้

เหตุผล: ภาษีเป็นข้อมูลระดับนิติบุคคลและสาขา จึงต้องมีแหล่งข้อมูลกลางชุดเดียวเพื่อป้องกันค่าไม่ตรงกัน
ระหว่าง POS, จัดซื้อ และบัญชี

## 3. In Scope

- Company Tax Profile
  - ชื่อกิจการตามเอกสารจดทะเบียน
  - เลขผู้เสียภาษี 13 หลัก
  - สถานะและวันที่จด VAT
  - ที่อยู่จดทะเบียน
  - รูปแบบราคา รวม VAT / ไม่รวม VAT / ยกเว้น VAT
  - อัตรา VAT เริ่มต้น
  - การยื่น ภ.พ.30 แบบแยกสาขาหรือยื่นรวมพร้อมสถานะอนุมัติ
- Branch Tax Profile
  - รหัสสาขาภาษี 5 หลัก
  - สำนักงานใหญ่ต้องเป็น `00000` และมีได้หนึ่งแห่งต่อ Company
  - ชื่อ/ที่อยู่/วันที่จด VAT ของสาขา
  - ช่วงวันที่มีผลและสถานะรวมในรายงานภาษี
- Tax Rate Rule
  - Standard, 0% และ Exempt
  - รูปแบบราคาและช่วงวันที่มีผล
  - อัตราเริ่มต้นหนึ่งรายการต่อช่วงเวลา
  - ป้องกัน code หรืออัตราเริ่มต้นซ้อนช่วงเวลา
- Audit log เก็บผู้แก้ เหตุผล IP/User Agent และค่าก่อน–หลัง
- e-Tax ดึงชื่อ ที่อยู่ เลขผู้เสียภาษี และรหัสสาขาจาก Tax Profile ตามวันที่ขาย
- หน้า Company Admin `/settings/tax`

## 4. Out of Scope

- การยื่น ภ.พ.30 หรือเอกสารต่อกรมสรรพากรโดยตรง
- Digital certificate, digital signature และ e-Tax Service Provider
- การคำนวณ Output VAT ใหม่จากยอดขายทุกช่องทาง (งาน WP9-B)
- ภาษีซื้อจาก Goods Receipt / Supplier Invoice reconciliation ใหม่ (งาน WP9-C)
- ภาษีหัก ณ ที่จ่ายเพิ่มเติมนอก AP ที่มีอยู่
- การเปิดใช้งานบน Production

## 5. Data Model และ Migration

Migration: `p15taxset0017` ต่อจาก `p14dist0016`

- `company_tax_profiles`
- `branch_tax_profiles`
- `tax_rate_rules`

Migration เป็น additive และ `downgrade` ลบเฉพาะสามตารางใหม่ ไม่มีการ rewrite ข้อมูลขาย/ซื้อเดิม

## 6. API

| Method | Route | สิทธิ์ | ผลลัพธ์ |
|---|---|---|---|
| GET | `/api/v1/tax-settings` | company view/edit หรือ accounting report | อ่านค่าภาษีรวม |
| PUT | `/api/v1/tax-settings/company` | `system.company.edit` | บันทึกข้อมูลบริษัท |
| PUT | `/api/v1/tax-settings/branches/{branch_id}` | `system.company.edit` | บันทึกข้อมูลสาขาภาษี |
| POST | `/api/v1/tax-settings/rates` | `system.company.edit` | เพิ่มอัตราตามช่วงเวลา |
| PATCH | `/api/v1/tax-settings/rates/{rule_id}` | `system.company.edit` | ปรับ/ปิดอัตรา |

ทุก route ใช้ Company ID จาก signed token และไม่รับ Company ID จาก client

## 7. Acceptance Criteria

- [x] เลขผู้เสียภาษีถูก normalize และต้องมี 13 หลัก
- [x] กิจการจด VAT ต้องมีเลขผู้เสียภาษีและที่อยู่
- [x] สำนักงานใหญ่ใช้ `00000` และ Company มีสำนักงานใหญ่ได้หนึ่งแห่ง
- [x] รหัสสาขาภาษีไม่ซ้ำกันภายใน Company
- [x] Standard / 0% / Exempt ผ่าน business validation
- [x] ช่วงวันที่ของ code เดียวกันและอัตราเริ่มต้นไม่ซ้อนกัน
- [x] การแก้ไขทุกประเภทสร้าง AuditLog พร้อมเหตุผล
- [x] e-Tax ใช้ Tax Profile โดยยัง fallback ไปข้อมูลเดิมเพื่อไม่ทำลาย legacy flow
- [x] Frontend type-check และ production build ผ่าน
- [x] Migration จากฐานข้อมูลว่างถึง head ผ่านในฐานข้อมูลทดสอบชั่วคราว
- [x] UAT ด้วยข้อมูลบริษัท/สาขาจำลอง
- [ ] UAT บนข้อมูลจดทะเบียนจริง — รอข้อมูลและ owner sign-off

## 8. Verification Evidence

- Backend full regression: `338` tests ผ่าน, skip `1`
- Backend focused tax settings: `10` tests ผ่าน
- Alembic fresh database migration: `p15taxset0017 (head)` ผ่าน
- Frontend TypeScript: ผ่าน
- Frontend production PWA build: ผ่าน (`4,208` modules)
- `git diff --check`: ผ่าน

## 9. UAT Deployment Evidence

- Feature commit: `a08122a9a786b030b1103e34dba2c1d6022b6fb0`
- UAT audit snapshot fix: `74f3e928427c8a7ecf48f236c332b8e58cf2c276`
- UAT URL: `https://uat-pos.foodchainservice.com`
- Backend image: `restaurant-pos-backend:wp9-74f3e92`
- Frontend image: `restaurant-pos-frontend:wp9-a08122a`
- Nginx image: `restaurant-pos-nginx:wp9-a08122a`
- Migration: `p16taxops0018 (head)` ซึ่งรวม `p15taxset0017`
- Backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/a08122a`
- Internal/public live และ ready health: HTTP `200`
- UAT auto-login และ `GET /api/v1/tax-settings`: HTTP `200`
- บันทึกบริษัทจำลอง, สำนักงานใหญ่, สาขา และ seed อัตรา Standard/0%/Exempt สำเร็จ
- Regression test ของ audit snapshot ผ่าน และ backend ไม่มี error หลังทดสอบ
- Production ไม่ถูกเปลี่ยนแปลง

## 10. Rollback

ก่อน deploy ให้ backup ฐานข้อมูลตาม runbook ปัจจุบัน หากต้องถอยกลับ:

1. หยุดการแก้ไขค่าภาษีชั่วคราว
2. ถอย application image/commit
3. downgrade migration จาก `p15taxset0017` ไป `p14dist0016`
4. e-Tax จะ fallback ไป `companies.tax_id`, `companies.name`, `companies.address` และรหัส `00000`

## 11. งานถัดไป

`WP9-B — Sales VAT Ledger and Output VAT Reconciliation`

- สร้าง sales tax ledger จากยอดขายที่ completed ทุก POS
- reconcile กับ full/abbreviated tax invoice, credit note, refund และ void
- สรุป Output VAT ราย Company/Branch/Brand/Module
- ยังไม่ยื่นข้อมูลจริงจนกว่าจะผ่าน UAT และ owner sign-off
