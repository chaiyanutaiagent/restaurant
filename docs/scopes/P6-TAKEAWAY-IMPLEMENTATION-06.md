# P6-TAKEAWAY-IMPLEMENTATION-06 — Dark Launch Implementation Record

วันที่ตรวจรับอัตโนมัติ: 2026-09-11

สถานะ: **implemented_dark_launch — source พร้อมทดสอบ แต่ feature ปกติปิดและยังไม่ deploy**

## ขอบเขตที่ส่งมอบ

- Takeaway Database, engine/session, fail-closed readiness และ Alembic chain แยกถึง
  `p6takeaway0004`; database name ต้องไม่ซ้ำ Legacy/Platform/Restaurant
- Control Plane reference projection และ authorization ด้วย `takeaway.*` permissions
- Catalog, branch availability, shift, paid-first sale, offline idempotency, payment, receipt,
  Kitchen, Pickup และ public customer QR ordering
- central order/round, production, stock ledger, shared raw-material stock หลายแบรนด์ภายใน
  Company, transfer, franchise credit และ sales report
- versioned ERP outbox/acknowledgement/reconciliation ที่ replay แล้วไม่เกิดผลซ้ำ
- paired device workspace สำหรับ Counter/KDS/Pickup ใน Takeaway context
- Chambo data contract, offline validator, synthetic importer, immutable historical archive,
  opening stock/credit และ reconciliation แบบไม่สร้าง historical side effect
- หน้า web/PWA: Dashboard, Counter, Kitchen, Pickup, Central Orders, Production, Stock,
  Transfers, Credits, Reports, Import, ERP, Customer Order และ Public Pickup Status

## Security และ Business Invariants

- request เลือก database เองไม่ได้; server เลือก session จาก business context ที่ผ่านการยืนยัน
- Takeaway context ไม่เปิด Restaurant/Retail operational session และข้อมูลทุก record แยก
  Company/Brand/Branch ตามขอบเขต
- ordering/pickup token เก็บเฉพาะ SHA-256 hash, จำกัดอายุ และ public ordering ถูก rate-limit
- QR ลูกค้าสั่งสร้างเพียง draft `awaiting_payment`; Kitchen ticket, stock movement, receipt และ
  ERP outbox เกิดหลังพนักงาน capture payment สำเร็จเท่านั้น
- idempotency key เดิมคืนผลเดิมทั้ง sale, public order, payment capture, ERP ack และ import
- historical import ห้ามสร้าง payment, notification, printer หรือ ERP event
- source `/Users/user/Projects/erp-pos-run` ถูกใช้เป็น reference แบบ read-only และไม่ถูกแก้ไข

## หลักฐานอัตโนมัติ

| Gate | ผล |
| --- | --- |
| Backend regression | `251` tests ผ่าน |
| Frontend | Type-check และ production build ผ่าน |
| Takeaway end-to-end smoke | sale/payment/queue/Kitchen/Pickup/stock/central/production/transfer/credit/report/ERP ผ่าน |
| Customer QR smoke | awaiting payment ไม่มี Kitchen ticket; capture ซ้ำคืนผลเดิม; Pickup status ผ่าน |
| Shared raw stock | สองแบรนด์ตัดกองเดียวและคงเหลือ `5.0000` ตาม expected |
| Synthetic Chambo import | 10 records; opening stock `50.0000`; credit `1500.00`; import ซ้ำไม่เพิ่ม; historical side effect `0` |
| Dependency/security scan | backend ไม่มี known vulnerability, frontend production audit `0`, secret scan ไม่พบ finding |
| Boundary backup/restore | dump 3 ฐานพร้อม SHA-256; isolated restore ตรวจ metadata ผ่านและลบฐาน drill แล้ว |

Backup ล่าสุดของรอบนี้อยู่ชั่วคราวที่
`/private/tmp/fcs-p6-boundary-backups/restaurant-boundaries-local-20260911T154835Z` และตั้ง
permission แบบ owner-only ใช้เพื่อพิสูจน์ rollback ไม่ใช่ production backup

## สิ่งที่ยังไม่อนุญาตและยังไม่ถือว่าเสร็จ

- ไม่ deploy ขึ้น `uat-pos.foodchainservice.com` หรือ Production และไม่เปลี่ยน Cloudflare Tunnel
- ไม่เปิด `TAKEAWAY_FEATURE_ENABLED` ใน runtime ปกติหรือเปิด entitlement ให้ลูกค้าจริง
- ไม่ต่อ Chambo production, ไม่สร้าง real export/snapshot และไม่ execute migration/cutover
- ยังไม่ผ่าน physical iPad/touch, เครื่องพิมพ์จริง, network interruption และ offline field UAT
- ยังไม่มี Restaurant Completion, Security/Operator/Platform Owner activation sign-off

เมื่ออุปกรณ์พร้อม ให้กลับไปทำ field UAT ด้วย release commit ที่ pin แล้ว แก้เฉพาะ defect ที่พบ
จากนั้น refresh audit/backup และขอคำสั่ง activation/deploy แยกต่างหาก
