# WP5-PHASE-GATE-02 — Company Shared Central Kitchen Verification

วันที่ตรวจรับอัตโนมัติ: 2026-09-14

สถานะ: **passed_local — implementation ทั้ง WP5-A ถึง WP5-D ผ่าน local gate; write path ยังปิดและยังไม่ deploy UAT/Production**

Baseline rollback: WP4 commit `5706e4ec2eea6ab5686d3f5770a648ffe0e8ed05`

## สิ่งที่ส่งมอบ

- ownership contract ของ Company kitchen, canonical ingredient, lot/ledger, demand, production และ Brand READY stock
- วัตถุดิบ Company identity หนึ่งตัวที่ Brand recipe หลายสูตร map มาใช้ร่วมกันได้
- FIFO issue จาก lot กลาง, idempotent receipt/demand/order/completion, reversal และ no-negative concurrency guard
- production output และต้นทุนแยก Brand พร้อม reuse Stock/Transfer ledger เดิมสำหรับ finished goods
- Company Admin `/company-kitchen` สำหรับภาพรวม setup/mapping, demand/production และรายงานแยก Brand
- dedicated permissions และ write feature flag ที่ปิดโดยค่าเริ่มต้น

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | `296` tests ผ่าน |
| WP5 focused unit/API | `11` tests ผ่าน: unit conversion, FIFO, ownership/role, signed Company API และ dark-launch write gate |
| Isolated PostgreSQL rehearsal | backup/restore legacy clone, upgrade `p13kitchen0015`, smoke, downgrade `p12route0014`, re-upgrade และ smoke ซ้ำผ่าน |
| Multi-brand fixture | “หมูแดดเดียว” และ “หมูหนักย่าง” ตัด canonical หมูกองเดียว แต่ READY output/report แยก Brand |
| Replay/reversal | receipt/completion/reversal replay ไม่สร้างซ้ำ; reversal คืน lot เดิมและหัก READY output |
| Concurrency | สองใบผลิตแย่ง RAW 1,500 g: สำเร็จหนึ่งใบ อีกใบถูกบล็อก `409`; ยอดไม่ติดลบ |
| Tenant isolation | Company อื่นอ่าน ingredient/order ของ fixture ไม่ได้ |
| Live local safety | fingerprint migration/company/brand/stock movement/table ก่อนและหลัง rehearsal ตรงกัน |
| Frontend type-check/build | ผ่าน; production/PWA build `4,205` modules transformed |
| Browser regression | Company Kitchen `1/1` และ Platform/Workspace `18/18` ผ่าน |
| UAT device suite | พักตามคำสั่ง owner; ไม่ใช้ credential/session ของ UAT ใน local gate |
| UAT/Production activation | ไม่ได้ดำเนินการ; `COMPANY_KITCHEN_WRITES_ENABLED=false` |

## Security และ accounting behavior

- Company มาจาก signed token และทุก Brand/Branch/Product/Location ถูกตรวจว่าอยู่ tenant เดียวกัน
- branch role รับ `company.kitchen.*` ไม่ได้; Company Owner preset ได้ view/manage
- RAW movement มี Company/kitchen/location/ingredient/lot/source และ Brand/production order เมื่อเป็นการผลิต
- receipt ระดับ Company ไม่บังคับ Brand; production issue/reversal และ finished output ระบุ Brand เสมอ
- report แยก Brand และคำนวณช่วงวันด้วย timezone ครัวกลาง (`Asia/Bangkok` โดยค่าเริ่มต้น)
- ไม่ import Chambo production data และไม่สร้าง Hotel schema

## คำเตือนที่ไม่บล็อก local gate

- physical Safari/iPad/UAT flow ยังต้องทดสอบโดย owner ก่อนเปิด write path
- production build มี large chunk warning เดิม ควรแยกแก้ใน performance work package
- test fixture ใช้ JWT key สั้นกว่า production recommendation; production secret ต้องผ่าน security checklist เดิม

## Rollback

- ปิด write flag ก่อนเสมอ; operational POS/ERP เดิมยังทำงานโดยไม่พึ่ง shared kitchen tables
- export/reconcile append-only ledger และ READY stock ก่อน rollback schema
- downgrade ได้เฉพาะเมื่อไม่มีรายการจริงที่ยังต้องเก็บ หรือ restore ได้จาก backup/manifest ที่ตรวจแล้ว
- ห้ามเปิด UAT/Production หรือรวม stock เดิมจากชื่อ/SKU โดยไม่มี owner sign-off

งานถัดไป: owner ทำ physical UAT และเตรียม opening-lot mapping; การเปิด write/deploy เป็นคำสั่งแยก
