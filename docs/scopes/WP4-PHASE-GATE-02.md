# WP4-PHASE-GATE-02 — Shared ERP Reporting Verification

วันที่ตรวจรับอัตโนมัติ: 2026-09-14

สถานะ: **passed_local — พร้อมส่งต่อ WP5; ยังไม่ deploy UAT/Production**

Baseline rollback: WP3 commit `70e38586fe95c5f01a192cdb9e1caa68d4169a59`

## สิ่งที่ส่งมอบ

- ownership matrix ระหว่าง Platform, ERP, Restaurant, Takeaway, Retail, Central Kitchen และ Hotel
- Platform reporting fact ที่แยก Company/module/business type/Brand/Branch/business date/source document
- exactly-once receipt, latest-event correction, refund/void reversal และ independent source cursor
- dead-letter/retry/freshness contract โดยไม่แสดงข้อมูลเก่าว่าเป็นข้อมูลล่าสุด
- server-side dimension verification และ Company Admin-only read API
- Company Admin `/reports/company` ที่รวมยอดแต่ยังแยก 3 POS และ Workspace
- dark-by-default projector ซึ่งเปิดไม่ได้ก่อน Platform identity/reference projection พร้อม

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | `285` tests ผ่าน |
| WP4 focused contract/API | `22` tests ผ่าน รวม Bangkok business date และ Takeaway refund normalization |
| Isolated PostgreSQL rehearsal | clone/restore, upgrade, smoke, downgrade, re-upgrade และ smoke ซ้ำผ่าน |
| Projection behavior | dedupe, correction ordering, partial/full refund, void และ tenant isolation ผ่าน |
| Reconciliation fixture | 4 Company facts, 7 receipts, 3 modules; gross/refund/net ตรง exact `0.01 THB` |
| Live local safety | Platform migration/company/brand/branch/report-table fingerprint ก่อนและหลังตรงกัน |
| Frontend type-check | ผ่าน |
| Frontend production/PWA build | ผ่าน; `4,204` modules transformed |
| Browser regression | `18` Playwright tests ผ่าน รวม Company shared report |
| UAT/Production activation | ไม่ได้ดำเนินการ; projector ยังคงปิดโดยค่าเริ่มต้น |

Migration heads ใน source ที่ตรวจแล้ว:

| Database | Head |
| --- | --- |
| Legacy/ERP | `p12route0014` |
| Platform core | `p13platform0017` |
| Restaurant | `p6restaurant0007` |
| Takeaway | `p6takeaway0004` |

ฐาน Platform local จริงยังอยู่ baseline เดิม `p12platform0016`; migration WP4 รันเฉพาะ clone ชั่วคราว
`restaurant_wp4_reporting_*` และถูกลบหลัง rehearsal

## Security และ behavior ที่ยืนยันแล้ว

- Company มาจาก signed token/source event; request ไม่มี Company/database write target
- Brand, Branch, business type และ active BrandBranch ต้องอยู่ Company เดียวกันก่อนเขียน
- receipt ไม่เก็บ source payload หรือข้อมูลลูกค้า เก็บเฉพาะ digest และ metadata ที่ allow-list
- Company อื่นไม่ปรากฏใน aggregate, Workspace หรือ recent documents
- event ซ้ำไม่สร้างยอดซ้ำ; event เก่าไม่ทับ correction ใหม่; refund/void มี event/receipt ย้อนกลับได้
- Hotel ไม่อยู่ใน reporting module allow-list และไม่มี operational schema
- source outbox ไม่ถูก mark processed โดย reporting worker จึงไม่แย่ง consumer เดิม
- report ประกาศ `projection_mode=shadow` และ `is_source_of_truth=false` เสมอ

## Rollback

- ปิด route/menu รายงานรวมและคง `SHARED_REPORTING_PROJECTOR_ENABLED=false`
- revert WP4 code ไป baseline WP3; operational POS และรายงานต้นทางไม่ขึ้นกับ projection
- ถ้าเคย migrate Platform ให้หยุด worker แล้ว downgrade `p13platform0017` → `p12platform0016`
- projection เป็น derived data จึง rebuild ได้; ห้ามแก้หรือลบ source sale/order เพื่อ rollback

## คำเตือนที่ไม่บล็อก gate

- production build ยังมี large chunk warning เดิม; แยกแก้ใน performance work package
- test JWT key 30 bytes เป็น development fixture เดิม; production ต้องใช้อย่างน้อย 32 bytes
- physical Safari/iPad UAT ของ Restaurant Phase 5 ยังพักไว้ตามคำสั่งเจ้าของระบบ
- ก่อนเปิด projector/UAT ต้อง migrate Platform, เปิด identity/reference projection ตามลำดับ และทำ
  reconciliation กับรายงานต้นทางจริง โดยต้องได้รับอนุมัติแยก

งานถัดไป: `docs/scopes/WP5-CENTRAL-KITCHEN-SHARED-STOCK-01.md`
