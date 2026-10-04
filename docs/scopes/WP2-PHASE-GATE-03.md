# WP2-PHASE-GATE-03 — Company Module Access Verification

วันที่ตรวจรับอัตโนมัติ: 2026-09-13

สถานะ: **passed_local — พร้อมส่งต่อ WP3; ยังไม่ deploy UAT/Production**

Baseline rollback: `pre-foodchainservice-platform-20260913`

## สิ่งที่ส่งมอบ

- stable server module allowlist: `erp`, `central_kitchen`, `restaurant_pos`,
  `takeaway_pos`, `retail_pos`, `hotel_pms`
- Company endpoint `GET /api/v1/membership/modules` ที่ผูก Company จาก signed tenant session
- Platform Owner endpoints สำหรับอ่านและเปิด/ปิดโมดูลราย Company พร้อม reason และ Audit Log
- effective-access policy ที่แยก plan inclusion, Company switch, lifecycle, permission และ runtime
- compatibility mapping จาก `restaurant`, `takeaway`, `retail_pos` ไป canonical module keys
- workspace selector และ Company Admin dashboard อ่านสถานะจาก server
- Platform Company detail แสดงสถานะแต่ละชั้นและควบคุม Company switch ได้
- billing plan change ไม่เขียนทับ module switch ที่ Platform Owner ตั้งไว้

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend compile | ผ่านด้วย Python 3.11 image |
| Backend full regression | `263` tests ผ่าน |
| API contract tests | tenant scope, Platform update และ mandatory reason ผ่าน |
| Module policy tests | allowlist, legacy mapping, plan/company/runtime/permission และ audit ผ่าน |
| Frontend type-check | ผ่าน |
| Frontend production/PWA build | ผ่าน; 4,202 modules transformed |
| Browser regression | `16` Playwright tests ผ่าน |
| Company Admin module status | แสดง plan/company/runtime จาก server response |
| Platform Owner control | แสดง 6 modules และ audit reference |
| Migration | ไม่มี schema/data migration; heads เดิมไม่เปลี่ยน |
| UAT/Production activation | ไม่ได้ดำเนินการ |

Migration heads ที่ตรวจแล้ว:

| Database | Head |
| --- | --- |
| Legacy/ERP | `p12route0014` |
| Platform core | `p12platform0016` |
| Restaurant | `p6restaurant0007` |
| Takeaway | `p6takeaway0004` |

## Security และ compatibility

- tenant module endpoint ไม่มี `company_id` จาก client และใช้ Company จาก access token เท่านั้น
- Platform read/update ต้องผ่าน active Platform session และ Platform Owner role
- update endpoint รับเฉพาะ stable key และ boolean จริง พร้อม reason ที่ไม่ว่าง
- Restaurant/Takeaway canonical switches sync กลับ legacy key เพื่อให้ backend guard เดิมยังทำงาน
- Hotel ยังคง `planned` และ runtime unavailable เสมอใน WP2
- Takeaway ยังคง `dark_launch`; ต้องผ่าน runtime flag เพิ่มเติมก่อน effective access
- Retail และ Central Kitchen ยังใช้ operational boundary เดิม; WP2 ไม่ย้ายตารางหรือข้อมูล

## Rollback

- revert frontend server-state integration ก่อน แล้ว revert module API/service
- ไม่มี migration จึงไม่ต้อง restore database สำหรับ rollback ปกติ
- module updates ที่เกิดภายหลัง deploy ต้องย้อนด้วย Platform UI พร้อม reason แทนการแก้ JSON ตรง
- disaster fallback ใช้ tag `pre-foodchainservice-platform-20260913` และ WP0 backup

## คำเตือนที่ไม่บล็อก gate

- production build ยังมี large chunk warning เดิม; แยกแก้ใน performance work package
- backend test ใช้ development JWT key 30 bytes; production activation ต้องใช้ secret อย่างน้อย 32 bytes
- physical Safari/iPad UAT ของ Restaurant Phase 5 ยังพักไว้ตามคำสั่งเจ้าของระบบ
