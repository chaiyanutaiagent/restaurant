# WP6-PHASE-GATE-02 — Supply Chain Distribution Verification

วันที่ตรวจรับอัตโนมัติ: 2026-09-14

สถานะ: **passed_local — WP6-A ถึง WP6-D ผ่าน local automated gate; write path ยังปิดและยังไม่ deploy UAT/Production**

Baseline rollback: WP5 commit `557e31eb0d418e6e3547dd3fc64286e0c3c8e3ce`

## สิ่งที่ส่งมอบ

- normalized demand contract สำหรับ Restaurant POS, Takeaway POS และ Retail POS
- validation ของ signed Company + Module/Brand/Branch/READY Product/Location
- shipment orchestration ที่ reuse TransferOrder/StockMovement เดิมสำหรับ reserve, dispatch, receive และ reverse return
- append-only planned/dispatched/received/rejected/returned/cancelled event audit พร้อม idempotency fingerprint
- reconciliation แยก Module/Brand/Branch: shipped, received, rejected, returned, in-transit และ net-received
- Company Admin `/company-distribution`, dedicated permissions และ write flag ที่ปิดโดยค่าเริ่มต้น
- แก้เลข Transfer ให้ลำดับ/lock ตรงกับ global unique constraint ป้องกันเลขชนข้าม Company

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | `304` tests ผ่าน |
| WP6 focused unit/API | `8` tests ผ่าน: module mapping, reconciliation invariants, company-only permissions, signed Company API และ dark-launch gate |
| Isolated PostgreSQL rehearsal | backup/restore legacy clone, upgrade `p14dist0016`, smoke, downgrade `p13kitchen0015`, re-upgrade และ smoke ซ้ำผ่าน |
| Three-POS fixture | Restaurant รับครบ, Takeaway reject ทั้งใบ, Retail รับแล้วคืนบางส่วน; ownership/reconciliation แยกถูกต้อง |
| Stock authority | plan จองผ่าน Transfer; dispatch/receive/return สร้าง StockMovement เดิมรวม `7` movement ใน fixture; WP6 ไม่มี stock balance ชุดใหม่ |
| Replay/conflict | demand replay ไม่สร้างซ้ำ; key เดิม payload ต่างถูกบล็อก `409` |
| Reservation safety | Shipment สองใบแย่ง READY คงเหลือ: ใบเกิน available ถูกบล็อกก่อนสร้างยอดจองซ้ำ |
| Tenant/module isolation | Company อื่นอ่าน fixture ไม่ได้; `retail_pos` demand ใช้ Restaurant Brand ถูกบล็อก |
| Live local safety | fingerprint migration/company/transfer/stock movement/table ก่อนและหลัง rehearsal ตรงกัน |
| Frontend type-check/build | ผ่าน; production/PWA build `4,206` modules transformed |
| Browser regression | Company Distribution `1/1`, Company Kitchen `1/1`, Platform/Workspace `18/18` ผ่าน |
| Physical UAT | พักตามคำสั่ง owner |
| UAT/Production activation | ไม่ได้ดำเนินการ; `COMPANY_DISTRIBUTION_WRITES_ENABLED=false` และ `COMPANY_KITCHEN_WRITES_ENABLED=false` |

## Security และ accounting behavior

- API ไม่รับ Company ID เป็น source of authority; ใช้ signed token และ server-side ownership checks
- branch-assignable role ถือ `company.distribution.view/manage` ไม่ได้; Company Owner preset ได้ทั้งสอง permission
- Takeaway ไม่ถูก query ข้ามฐาน; ใช้ normalized demand/outbox contract เมื่อเปิด integration ภายหลัง
- reject ไม่เพิ่ม stock ขายและแสดงเป็น discrepancy แยก; return หลังรับใช้ reverse Transfer ที่ตรวจย้อนหลังได้
- ไม่มี customer PII, payment หรือ receipt ถูก copy เข้า distribution tables
- report เลือก Shipment ที่มี event ในช่วงวันตาม `Asia/Bangkok` และแสดง current reconciliation ของ Shipment เหล่านั้น

## คำเตือนที่ไม่บล็อก local gate

- physical Safari/iPad flow และการสแกนเอกสารส่งมอบจริงยังต้องทดสอบก่อนเปิด write
- production build มี large chunk warning เดิม ควรแก้ใน performance work package แยก
- test JWT key warning เป็น fixture เดิม; production secret ต้องใช้ security checklist เดิม
- reject discrepancy ต้องมีขั้นตอนปฏิบัติจริงว่าของเสีย/สูญหาย/กลับเข้าคลังใด ก่อน rollout

## Rollback

1. ปิด `COMPANY_DISTRIBUTION_WRITES_ENABLED` ก่อน
2. export/reconcile demand, shipment, event, linked Transfer และ StockMovement manifest
3. POS/ERP/Transfer เดิมทำงานต่อได้โดยไม่พึ่ง WP6
4. downgrade `p14dist0016 → p13kitchen0015` เฉพาะเมื่อยังไม่มีข้อมูลจริงหรือมี restore ที่ตรวจแล้ว
5. ไม่เปิด WP5/WP6 flags, migrate หรือ deploy UAT/Production โดยไม่มี owner sign-off

งานถัดไป: พัก physical UAT ต่อได้; Work Package ถัดไปควรเป็น WP7 Retail POS SaaS Alignment contract
ก่อน implement โดยไม่เปิด WP5/WP6 write path อัตโนมัติ
