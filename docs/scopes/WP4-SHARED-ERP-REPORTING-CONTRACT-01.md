# WP4-SHARED-ERP-REPORTING-CONTRACT-01 — Shared ERP และรายงานรวมข้ามโมดูล

วันที่วางแผน: 2026-09-13

สถานะ: **next_planned — ยังไม่เริ่ม implementation**

Baseline: WP3 gate บน branch `codex/foodchainservice-platform`

## เป้าหมาย

กำหนด contract ให้ Restaurant POS, Takeaway POS และ Retail POS ใช้ ERP กลางของ Company ร่วมกัน
แต่ยอดขาย ต้นทุน สต๊อก และรายงานยังจำแนกตามโมดูล Brand และ Branch ได้ โดยไม่ join operational
database ข้าม boundary ตรง ๆ และไม่เปิด Hotel ก่อนมี schema จริง

ผลที่ต้องการคือ Company Admin เห็นทั้งภาพรวมบริษัทและ drill-down ไปยังระบบต้นทางได้ ขณะที่
operational module แต่ละตัวส่งข้อมูลสรุปแบบ idempotent เข้าชั้นรายงานกลางเท่านั้น

## งานในขอบเขต

### WP4-A — Ownership และ reporting dimensions

- inventory/product/accounting ใดเป็น Company shared master และใดเป็น operational-owned data
- stable dimensions: `company_id`, `module_key`, `business_type`, `brand_id`, `branch_id`,
  `source_document_type`, `source_document_id` และ business date/timezone
- mapping Restaurant/Takeaway/Retail เดิมโดยไม่เปลี่ยน public route หรือ operational primary key
- Company-level stock location และ Central Kitchen dimension ต้องไม่บังคับย้ายฐานใน WP4

### WP4-B — Idempotent reporting ingestion

- สร้าง allow-listed reporting event/envelope จากแต่ละ operational boundary
- unique source identity ป้องกัน replay และรองรับ correction/reversal โดยไม่แก้ยอดแบบเงียบ
- ห้าม client เลือก Company หรือ database; server derive จาก signed context/event ownership
- dead-letter/retry/audit และ projection lag/readiness ต้องสังเกตได้

### WP4-C — Company Admin reports

- dashboard รวมแสดงยอดแยก Restaurant, Takeaway และ Retail ตาม module/brand/branch
- drill-down อ้างอิงกลับ source document โดยไม่เปิดข้อมูล tenant อื่น
- Hotel แสดง planned/no-data และห้ามถูกนับเป็นศูนย์แบบทำให้เข้าใจว่าเปิดใช้งานแล้ว
- ระหว่าง cutover ต้อง reconcile รายงานรวมกับผลรวมรายงานต้นทางตาม tolerance ที่กำหนด

### WP4-D — Gates และ rollout safety

- contract/unit/API tests สำหรับ tenant isolation, deduplication, replay, reversal และ timezone
- isolated migration/restore rehearsal หากต้องเพิ่ม reporting projection table
- synthetic Restaurant/Takeaway/Retail fixtures เท่านั้น; ไม่ import Chambo production data
- shadow/read-only comparison ก่อนเปิด dashboard เป็น source of truth
- ไม่มี UAT/Production activation จน reconciliation และ rollback gate ผ่าน

## นอกขอบเขต

- ไม่ย้าย Central Kitchen ออกจาก Restaurant database
- ไม่ตัดสต๊อก production จริงข้ามหลายแบรนด์ใน WP4
- ไม่ import `/Users/user/Projects/erp-pos-run` หรือข้อมูล Chambo จริง
- ไม่ redesign Restaurant/Takeaway/Retail POS transaction flow
- ไม่สร้าง Hotel operational schema
- ไม่เปิด billing collection หรือเปลี่ยน Cloudflare routes
- ไม่ rename repository, Docker project หรือ database

## Acceptance criteria

- [ ] shared/operational ownership matrix ถูกบันทึกและไม่มี table owner ซ้ำโดยไม่จำเป็น
- [ ] ทุก reporting record มี Company/module/Brand/Branch/source identity ที่ server ตรวจสอบได้
- [ ] replay ไม่สร้างยอดซ้ำ และ correction/reversal มี audit trail
- [ ] Company A อ่านหรือเขียน projection ของ Company B ไม่ได้
- [ ] รายงานรวมแยก Restaurant/Takeaway/Retail และ drill-down กลับต้นทางได้
- [ ] aggregate เท่ากับผลรวม source fixtures ตาม tolerance ที่กำหนด
- [ ] projection lag/failure แสดงเป็นสถานะ ไม่รายงานข้อมูลเก่าว่าเป็นข้อมูลล่าสุด
- [ ] ถ้ามี migration ต้องผ่าน isolated backup/restore และ downgrade rehearsal
- [ ] backend/frontend/browser regression ผ่าน
- [ ] ไม่มี UAT/Production activation ระหว่าง WP4

## Rollback

- ปิด shared reporting UI และหยุด projector/consumer ก่อน
- operational module ยังคงขายและใช้รายงานเดิมได้โดยไม่พึ่ง projection ใหม่
- projection เป็น derived data; rebuild ได้จาก event/source contract ที่ผ่าน audit
- migration ใด ๆ ต้องมี Scope Change, backup และ rollback drill แยกก่อนแก้ฐานจริง

## ลำดับหลัง WP4

เมื่อ shared ownership/reporting contract ผ่านแล้ว จึงวาง WP5 สำหรับ Central Kitchen production,
shared raw-material stock และคำสั่งผลิตข้ามแบรนด์ โดยใช้ dimensions และ audit contract จาก WP4
