# WP43 Server-Authoritative Price and Price Override Phase Gate

วันที่: `2026-09-20`
ผล: **PASS — local + UAT engineering gate; WP43 closed for UAT**
UAT: **Deployed at release `wp43-6b7b0c6`; smoke and rollback readiness passed**
Production: **Blocked / not approved**

## Scope accepted

- server-authoritative price, promotion, discount, VAT, rounding และ total
- Company/Brand/Branch/Channel/Customer/currency/effective-time price resolution
- price snapshot, version, quote expiry และ stale/context/version errors
- Price Override permission, reason, threshold, manager approval และ separation of duties
- idempotent calculate/checkout, replay protection และ concurrency locks
- append-only override audit และ sale/payment/stock reconciliation
- Restaurant/POS UI discrepancy, approval และ offline Stale/fail-closed states

## Gate evidence

- implementation/test commits `c8aa90b`, `51a6f5d` และ `6b7b0c6` อยู่ใน repository ที่กำหนด
- backend regression `408/408`, focused tests `24/24`, TypeScript และ production/PWA build ผ่าน
- migration upgrade/downgrade rehearsal ผ่าน และ UAT อยู่ที่ `wp43price0019`
- final UAT integration smoke ผ่าน authority/tamper/VAT/override/approval/idempotency/stale/offline/audit/reconciliation
- public routes และ health ผ่าน; recent HTTP `5xx` เท่ากับ `0`
- backup, previous immutable release/images และ application rollback พร้อมใช้
- UAT runtime/data-source/write flags เดิมไม่เปลี่ยน
- Production container IDs/images ไม่เปลี่ยน

หลักฐานฉบับเต็มอยู่ที่ `docs/scopes/WP43-UAT-DEPLOYMENT-03.md`

## Production blockers

- loyalty redemption ต้องเปลี่ยนจาก consume-before-sale เป็น reserve → commit/release แบบ idempotent
- Physical UAT เครื่องพิมพ์ เงินสด PromptPay และ network-loss workflow ยังอยู่ใน WP47
- Production ต้องมี approval gate แยกต่างหาก

## Deliberate non-actions

- ไม่มี Production deployment หรือ Production feature activation
- ไม่เริ่ม WP44 Server-backed Hold Draft
- ไม่เปลี่ยน Retail operational data source
- ไม่เปิด Takeaway/Central Kitchen real transactions
- ไม่สร้างหรือยื่นเอกสารภาษีจริง

## Decision

WP43 **PASS และ Closed สำหรับ Local/UAT engineering scope** แต่ยัง **ไม่ Production-ready** เพราะ loyalty
atomicity และ Physical UAT ยังไม่ผ่าน หยุดงานที่ WP43 ตามคำสั่งและรอ owner อนุมัติ WP44 แยกต่างหาก
