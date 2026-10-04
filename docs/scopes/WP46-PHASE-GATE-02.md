# WP46 Provider Refund + Tax/Credit Note Phase Gate

วันที่: `2026-09-20`
ผล: **PASS — local + UAT engineering gate; WP46 closed for UAT**
UAT: **Deployed at release `wp46-4c6c1a9`; smoke, visual UAT and rollback readiness passed**
Production: **Blocked / not approved**

## Scope accepted

- Server-authoritative refund quote จาก Sale/Payment/Tax snapshot เดิม
- exact-payload maker-checker, idempotency, optimistic version และ concurrent one-winner
- cash confirmation และ provider sandbox state machine พร้อม retry/inquiry/webhook reconciliation
- negative Payment ledger หลังทุก leg สำเร็จเท่านั้น
- explicit stock disposition และ loyalty earned-points reversal แบบ exactly-once
- synthetic `UAT NON-FISCAL` Credit Note หลัง refund success เท่านั้น
- close-shift blocker, reconciliation/reporting และ append-only audit
- touch-first Desktop/iPad Refund Workspace พร้อม loading/error/offline/unknown states

## Gate evidence

- implementation/test/accessibility commits `0da47bf`, `062532e`, `4c6c1a9` ถูก push ไป repository ที่กำหนด
- backend regression `432/432`, targeted contract `10/10`, TypeScript และ production/PWA build ผ่าน
- migration rehearsal และ final UAT migration `wp46refund0022` ผ่าน
- final UAT smoke ผ่าน quote, approval binding, cash/provider states, webhook, ledger, stock, loyalty,
  Credit Note, reconciliation, concurrency และ append-only controls
- Desktop/tablet visual UAT ผ่าน; browser console ไม่มี warning/error
- public routes/health ผ่าน และ recent HTTP `5xx` เท่ากับ `0`
- backup 5 databases + Redis + uploads และ checksum ผ่าน
- application rollback ไป WP45 และกลับ WP46 ผ่าน, RTO `9 seconds`
- Production container IDs/images ไม่เปลี่ยน

หลักฐานฉบับเต็มอยู่ที่ `docs/scopes/WP46-UAT-DEPLOYMENT-03.md`

## Production blockers

- live provider integration/credential/security/SLA ยังไม่อนุมัติ
- real Tax/Credit Note ต้องผ่าน Accountant/Tax Owner sign-off
- loyalty redeemed-points reserve/restore ต้อง atomic
- Physical UAT printer, cash, PromptPay, paired Counter/iPad และ network-loss workflow ยังไม่ผ่าน
- WP47 Offline/Sync ยังเป็น design/test plan และ `POS_OFFLINE_MODE_ENABLED=false`
- Production ต้องมี owner approval และ deployment gate แยกต่างหาก

## Deliberate non-actions

- ไม่มี Production deployment, migration หรือ Production feature activation
- ไม่เรียก live refund provider และไม่สร้าง/ยื่นเอกสารภาษีจริง
- ไม่เปลี่ยน Retail operational data source
- ไม่เปิด Takeaway/Central Kitchen transactions
- ไม่เปิด offline transaction mode

## Decision

WP46 **PASS และ Closed สำหรับ Local/UAT engineering scope** แต่ยัง **ไม่ Production-ready**
ลำดับถัดไปคือ WP47/Physical UAT ตาม gate ที่กำหนด โดยต้องคง feature flags อันตรายปิดไว้

