# WP45 Restaurant Cancellation Approval + Waste/Audit Phase Gate

วันที่: `2026-09-20`
ผล: **PASS — local + UAT engineering gate; WP45 closed for UAT**
UAT: **Deployed at release `wp45-600c6d4`; smoke, visual UAT and rollback readiness passed**
Production: **Blocked / not approved**

## Scope accepted

- Server-controlled cancellation policy ตามสถานะครัว `pending`, `cooking`, `done` และ `served`
- maker-checker approval สำหรับ cancellation หลังเริ่มทำและสำหรับ reopen
- full recipe Waste posting แบบ fail closed พร้อม stock movement ที่ตรวจสอบย้อนกลับได้
- structured cancellation receipt, reason, bill impact, requester/approver/device และ policy snapshot
- append-only Cancellation, Waste และ audit evidence ที่ DB ป้องกัน UPDATE/DELETE
- KDS cancellation event, acknowledge/replay และ exact scope ถึง Company/Brand/Branch/Station
- idempotency, canonical payload, row lock, optimistic version และ concurrent one-winner
- reopen เป็น order/ticket ใหม่ด้วยราคาปัจจุบัน โดยคงหลักฐาน/Waste เดิม
- touch-first desktop/tablet UI พร้อม loading, offline, error, blocker และ permission states

## Gate evidence

- implementation/accessibility commits `4fc67a7` และ `600c6d4` อยู่ใน repository ที่กำหนด
- backend regression `422/422`, TypeScript และ production/PWA build ผ่าน
- migration upgrade/downgrade rehearsal ผ่าน และ final UAT อยู่ที่ `wp45cancel0021`
- API smoke ผ่าน cancellation stages, approval, Waste, scope, idempotency, concurrency, reopen และ no-financial-side-effect cases
- append-only database trigger ครบ 3 ตัว
- desktop/tablet visual UAT ผ่าน; final dialog ไม่มี console warning/error
- public routes/health ผ่าน และ recent HTTP `5xx` เท่ากับ `0`
- backup 5 databases + Redis + uploads, checksum, image pinning และ rollback drill ผ่าน
- application rollback RTO `12 seconds`; สลับกลับ WP45 และรัน smoke ซ้ำผ่าน
- runtime/data-source/write flags เดิมไม่เปลี่ยน
- Production container IDs/images ไม่เปลี่ยน

หลักฐานฉบับเต็มอยู่ที่ `docs/scopes/WP45-UAT-DEPLOYMENT-03.md`

## Production blockers

- provider refund + payment-provider reconciliation ยังไม่อยู่ใน transaction/audit flow
- Tax/Credit Note และ real tax document ยังไม่ถูกสร้างหรือยื่น
- loyalty reserve → commit/release ยังไม่ atomic กับ Sale
- Physical UAT เครื่องพิมพ์ เงินสด PromptPay, paired Counter/iPad และ network-loss workflow ยังไม่ผ่าน
- Production ต้องมี owner approval และ deployment gate แยกต่างหาก

## Deliberate non-actions

- ไม่มี Production deployment, migration หรือ Production feature activation
- ไม่เริ่ม WP46 Provider Refund + Tax/Credit Note
- ไม่เปลี่ยน Retail operational data source
- ไม่เปิด Takeaway/Central Kitchen real transactions
- ไม่สร้างหรือยื่นเอกสารภาษีจริง

## Decision

WP45 **PASS และ Closed สำหรับ Local/UAT engineering scope** แต่ยัง **ไม่ Production-ready**
หยุดงานที่ WP45 ตามลำดับ CTO และรอ owner อนุมัติ WP46 แยกต่างหาก
