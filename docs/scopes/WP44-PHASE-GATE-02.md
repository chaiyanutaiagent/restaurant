# WP44 Server-backed Hold Draft Phase Gate

วันที่: `2026-09-20`
ผล: **PASS — local + UAT engineering gate; WP44 closed for UAT**
UAT: **Deployed at release `wp44-bfe6e4f`; smoke, visual UAT and rollback readiness passed**
Production: **Blocked / not approved**

## Scope accepted

- Server-backed Hold Draft ที่เห็นร่วมกันทุก Counter ภายใน Company/Brand/Branch
- owner/assignee/device/shift identity, TTL, expiry, reopen และ append-only audit
- idempotency, optimistic version และ concurrent claim แบบผู้ชนะหนึ่งราย
- WP43 server-authoritative price/availability revalidation ก่อน resume และก่อน checkout
- atomic Hold Draft → Sale conversion โดย Hold ไม่สร้าง payment/stock/tax side effect
- close-shift blocker, reassign พร้อมเหตุผล และ role/permission enforcement
- online/offline/reconnect/conflict/loading/empty/error/permission states
- touch-first desktop/tablet UI พร้อม search, filter, history และ safe cart replacement

## Gate evidence

- implementation/accessibility commits `b72ef3e` และ `bfe6e4f` อยู่ใน repository ที่กำหนด
- backend regression `412/412`, focused tests `24/24`, TypeScript และ production/PWA build ผ่าน
- migration upgrade/downgrade rehearsal ผ่าน และ final UAT อยู่ที่ `wp44hold0020`
- API smoke ผ่าน idempotency/concurrency/scope/revalidation/lifecycle/side-effect/audit/shift cases
- desktop/tablet visual UAT ผ่าน; final dialog ไม่มี console warning/error
- public routes/health ผ่าน และ recent HTTP `5xx` เท่ากับ `0`
- backup 5 databases + Redis + uploads, checksum, previous images และ rollback drill ผ่าน
- runtime/data-source/write flags เดิมไม่เปลี่ยน
- Production container IDs/images ไม่เปลี่ยน

หลักฐานฉบับเต็มอยู่ที่ `docs/scopes/WP44-UAT-DEPLOYMENT-03.md`

## Production blockers

- loyalty reserve → commit/release ยังไม่ atomic กับ Sale
- Physical UAT เครื่องพิมพ์ เงินสด PromptPay, paired Counter/iPad และ network-loss workflow ยังไม่ผ่าน
- Production ต้องมี owner approval และ deployment gate แยกต่างหาก

## Deliberate non-actions

- ไม่มี Production deployment, migration หรือ Production feature activation
- ไม่เริ่ม WP45 Restaurant Cancellation Approval + Waste/Audit
- ไม่เปลี่ยน Retail operational data source
- ไม่เปิด Takeaway/Central Kitchen real transactions
- ไม่สร้างหรือยื่นเอกสารภาษีจริง

## Decision

WP44 **PASS และ Closed สำหรับ Local/UAT engineering scope** แต่ยัง **ไม่ Production-ready**
หยุดงานที่ WP44 ตามคำสั่งและรอ owner อนุมัติ WP45 แยกต่างหาก
