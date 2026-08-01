# Scope ID: P4-REPORT-SCOPE-01

สถานะ: **Verified — scoped Restaurant ERP report foundation complete**
Phase: **Phase 4 — Restaurant ERP Core**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner
Business type: **restaurant**
Target database: **restaurant operational data ผ่าน rollback-safe legacy runtime default**

## Problem

Dashboard/report API เดิมกรอง `company_id` แต่รับ `branch_id` จาก query โดยยังไม่บังคับให้ตรงกับ
staff assignment ทำให้ผู้ใช้ Branch-scoped ที่มี `pos.report.view` สามารถขอข้อมูล Branch อื่นใน Company
เดียวกันได้ นอกจากนี้ consolidated Brand operations report ใช้ `fb.kitchen.manage` ซึ่ง Brand Manager
preset ไม่มี และ scope check เดิมยังไม่แยก Brand Manager ออกจาก Branch Manager ชัดเจน

## In Scope

- เพิ่ม report-scope policy เดียวสำหรับ Company/Brand/Branch/Station token context
- Company scope ดูรวม Company หรือเลือก Branch ได้
- Brand scope ใช้ generic dashboard/report ได้เฉพาะ Branch context ที่เลือก และใช้ Brand operations
  report เพื่อดูผลรวมเฉพาะ Brand ที่ได้รับมอบหมาย
- Branch/Station scope ถูกบังคับเป็น Branch ใน token แม้ client ส่ง `branch_id` อื่น
- shift summary/PDF ถูกล็อกด้วย Branch scope เช่นเดียวกับ sales dashboard
- เปลี่ยน Brand operations report เป็น `fb.report.view` และอนุญาตเฉพาะ Company/Brand scope
- เพิ่ม policy/API regression และอัปเดต route/permission/roadmap ตามพฤติกรรมจริง

## Database / Ownership

- ไม่มี migration และไม่มีตารางใหม่
- assignment/context เป็น Identity-owned; report query เป็น Restaurant operational concern
- ไม่มี cross-database SQL join หรือ foreign key
- runtime selector คง identity `legacy`, Restaurant service `legacy`, projector disabled
- `get_db` compatibility route ยังคงอยู่จนกว่าจะมี production cutover ที่อนุมัติแยก

## Out of Scope

- redesign dashboard UI หรือเพิ่มกราฟ/metric ใหม่
- recipe costing, stock/purchase/transfer migration และ accounting handoff ซึ่งแยก Scope ถัดไป
- payroll, AI forecast, CRM, franchise royalty และ Central Production batch changes
- production activation, deploy, APK/physical tablet UAT และ database selector change

## Acceptance Criteria

- [x] Company-scoped user ดู Company aggregate และเลือก Branch ภายใน Company ได้
- [x] Brand Manager เปิด consolidated report ได้เฉพาะ Brand ที่ได้รับมอบหมาย
- [x] Brand Manager generic dashboard ถูกจำกัดที่ Branch context ปัจจุบัน
- [x] Branch/Station-scoped user ส่ง `branch_id` อื่นแล้วได้ `404` โดยไม่เปิดเผยข้อมูล
- [x] Branch Manager เปิด Brand consolidated report ไม่ได้
- [x] shift summary และ PDF ข้าม Branch ถูกปฏิเสธ
- [x] existing dashboard/report response contract และ frontend route ยังใช้ได้
- [x] backend unit/API regression และ frontend type-check/build ผ่าน
- [x] ไม่มี schema/live-data mutation และ worktree commit โดยไม่ push

## Rollback

1. revert Scope commit เพื่อคืน report route policy เดิม
2. ไม่มี schema downgrade หรือ data repair
3. dashboard/report payload ไม่เปลี่ยน จึงไม่ต้อง rollback frontend state
4. runtime และ database boundaries ไม่เปลี่ยน

## Execution Record

- Starting commit: `a236a53`
- Report policy unit tests: 6 cases ผ่าน Company, superuser, Brand, Branch, Station และ missing context
- API matrix: Company aggregate/selected Branch, Brand current-Branch/consolidated report, Brand mismatch,
  Branch query isolation, consolidated deny และ shift/PDF isolation ผ่าน
- Assignment/approval regression: Company/Brand/Branch/Station, multi-role, revoke audit, Manager PIN,
  discount/void/refund/stock และ Restaurant checkout ผ่าน
- Migration rehearsal: legacy `p2approval0002`, Platform `p2platform0005`, Restaurant
  `p2restaurant0004` ผ่าน upgrade → downgrade → re-upgrade บน clone ชั่วคราว
- Backend regression: 162 tests ผ่าน
- Frontend regression: TypeScript type-check และ production/PWA build ผ่าน; มี chunk-size warning เดิม
- Live fingerprints ก่อน/หลังไม่เปลี่ยน: legacy `6b7c8d9e0f12:1:4:7:21:21`,
  Platform `p1platform0003:1:1:7:9`, Restaurant `p1restaurant0003:1:4:23:23`
- Temporary database cleanup: final query พบ rehearsal prefixes ค้าง `0`
- Main backend: หยุดตลอด gate; rollback-safe `restaurant-pos-dev-backend:latest` คง ID
  `sha256:578dd5339c9ea6791d075384e4a2b92cd8422738b809cd147fd6e4eb364cc8de`
- Scope artifact:
  `/private/tmp/restaurant-p4-artifacts/p4-report-scope-01-20260801T095039Z/manifest.txt`
- Reused assignment/approval artifact:
  `/private/tmp/restaurant-p4-artifacts/p2-approval-sessions-03-20260801T095039Z/manifest.txt`
- Production activation: `false`; ไม่มี deploy และไม่มี push
