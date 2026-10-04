# WP3-PHASE-GATE-02 — Company Workspace Provisioning Verification

วันที่ตรวจรับอัตโนมัติ: 2026-09-13

สถานะ: **passed_local — พร้อมส่งต่อ WP4; ยังไม่ deploy UAT/Production**

Baseline rollback: WP2 commit `4aca82e8a2b414255ba245808d24c5b643010d5d`

## สิ่งที่ส่งมอบ

- Company Workspace directory จาก server ที่จัด ERP, Central Kitchen และ POS ตาม hierarchy เดียวกัน
- Company Admin route `/workspaces` พร้อมรายการ Brand/Branch แยกตาม Restaurant, Takeaway,
  Retail และ Hotel planned state
- idempotent Restaurant workspace provisioning จาก Company/Brand/Branch contract เดิม
- server-owned business type/entry route โดย client ไม่มี field สำหรับเลือก target database
- plan, module, permission, tenant และ Company lifecycle guard ก่อน write
- workspace deactivate/reactivate พร้อมเหตุผลและ Audit Log โดยไม่ลบประวัติเดิม
- Platform reference outbox สำหรับ identity aggregate เมื่อใช้ split identity database

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | `273` tests ผ่าน |
| Workspace unit/API contract | normalization, permission, signed tenant, idempotency และ unsafe field rejection ผ่าน |
| Isolated PostgreSQL rehearsal | provisioning, replay, plan limit, tenant isolation, audit และ rollback status ผ่าน |
| Live local safety | fingerprint ของ migration/company/brand/branch/audit ก่อนและหลัง rehearsal ตรงกัน |
| Frontend type-check | ผ่าน |
| Frontend production/PWA build | ผ่าน; `4,203` modules transformed |
| Browser regression | `17` Playwright tests ผ่าน |
| Route compatibility | `/admin`, `/restaurant`, `/takeaway`, `/pos` และ auth guards เดิมผ่าน |
| Secret pattern scan | source ที่อยู่ในขอบเขตไม่พบ private key/access token pattern |
| Migration | ไม่มี schema/data migration; heads เดิมไม่เปลี่ยน |
| UAT/Production activation | ไม่ได้ดำเนินการ |

Migration heads ที่ตรวจแล้ว:

| Database | Head |
| --- | --- |
| Legacy/ERP | `p12route0014` |
| Platform core | `p12platform0016` |
| Restaurant | `p6restaurant0007` |
| Takeaway | `p6takeaway0004` |

## Security และ behavior ที่ยืนยันแล้ว

- directory และ mutation ใช้ Company ID จาก signed access token ไม่รับ tenant target จาก client
- ต้องมี `system.company.edit` หรือ Platform-level wildcard จึงจัดการ Workspace ได้
- Takeaway ยังปิดเมื่อ dark-launch runtime/plan/Company gate ไม่ครบ และ Hotel ไม่มี create contract
- idempotency key เดิมกับ payload ต่างกันถูกปฏิเสธ ส่วน key ใหม่กับ natural identity เดิมไม่สร้างซ้ำ
- Company อื่นเปลี่ยนสถานะ Workspace ไม่ได้และได้ผลแบบไม่เปิดเผยข้อมูล tenant
- deactivate/reactivate เปลี่ยน BrandBranch link เท่านั้น และทุกการเปลี่ยนจริงมี Audit Log
- rehearsal สร้างและลบเฉพาะฐาน `restaurant_wp3_workspace_*` ที่ clone จาก local source

## Rollback

- ซ่อน/ถอด Company Admin route `/workspaces` ก่อน แล้ว revert API/service ของ WP3
- คง Brand/Branch/BrandBranch ที่เคยสร้างไว้; ใช้ deactivate พร้อม reason แทนการลบข้อมูล
- ไม่มี migration จึงไม่ต้อง restore สำหรับ code rollback ปกติ
- หากเกิดเหตุระดับฐานข้อมูล ใช้ WP0 backup และ baseline ตามเอกสาร WP0

## คำเตือนที่ไม่บล็อก gate

- production build ยังมี large chunk warning เดิม; แยกแก้ใน performance work package
- backend test ใช้ development JWT key 30 bytes; production activation ต้องใช้ secret อย่างน้อย 32 bytes
- split-boundary Workspace อาจต้องรอ reference projector ก่อนเปิดครั้งแรก; WP4 ต้องกำหนด readiness
  contract ไม่ให้ frontend เดาสถานะเอง
- physical Safari/iPad UAT ของ Restaurant Phase 5 ยังพักไว้ตามคำสั่งเจ้าของระบบ
