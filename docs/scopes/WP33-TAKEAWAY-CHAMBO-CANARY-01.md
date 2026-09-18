# WP33 — Takeaway/Chambo Canary Readiness

วันที่: `2026-09-18`
สถานะ: **engineering_ready — approved source snapshot, physical UAT and canary sign-off pending**

## สิ่งที่พร้อมแล้ว

- Store, Central และ Admin workspace อยู่ใน Restaurant/Foodchainservice repository เดียว
- paid-first counter, queue, KDS, pickup, shift, stock, store ordering, production, credit และ reports
- local outbox สำหรับ offline/retry และ idempotent ERP event
- signed Chambo snapshot/import preview/execute/reconciliation/rollback tooling
- dedicated Takeaway database และ Platform reference projection
- permission และ operational database boundary แยกจาก Restaurant/Retail

## Automated evidence

| Gate | ผล |
| --- | --- |
| Takeaway/import/security focused tests | `36/36` ผ่าน |
| Takeaway browser role/offline/workspace | `5/5` ผ่าน |
| Static secret and DB-boundary scan | ผ่าน |
| Android identity/signing boundary | ผ่าน; native mobile ยังอยู่นอก release ปัจจุบัน |
| Production runtime | `TAKEAWAY_SERVICE_DATABASE=takeaway`, feature และ reference projector เปิด |
| Production schema | `takeaway_ops_db` head `p6takeaway0008` |

## Canary hard gates

- [ ] owner อนุมัติ Chambo source snapshot, scope และ SHA-256 โดยไม่มีข้อมูลนอกขอบเขต
- [ ] dry-run/import reconciliation ของ master/opening/history ผ่านกับ snapshot ที่อนุมัติ
- [ ] tablet, printer, QR/payment, KDS, pickup และ offline/reconnect ผ่านที่สาขาจริง
- [ ] final five-boundary backup และ isolated restore ผ่าน
- [ ] canary หนึ่งสาขาอย่างน้อย 60 นาที มี duplicate/stock/payment mismatch เท่ากับศูนย์
- [ ] owner อนุมัติ `go`; หากไม่ครบต้องใช้ rollback และคงหลักฐานไว้

## Decision

ระบบ Chambo เดิมไม่จำเป็นสำหรับการพัฒนา feature ต่อ แต่การปิดระบบเดิมและรับข้อมูลจริงต้องรอ
approved snapshot และ one-branch canary; automated result ห้ามใช้แทน owner decision
