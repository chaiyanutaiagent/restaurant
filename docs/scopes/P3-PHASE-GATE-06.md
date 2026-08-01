# Scope ID: P3-PHASE-GATE-06

สถานะ: **Verified — Phase 3 implementation gate complete; physical tablet/Android UAT deferred**
Phase: **Phase 3 — Dedicated Counter, Kitchen และ Device Pairing**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Phase 3 มี device pairing, dedicated workspace, offline authorization, Counter staff handover และ
durable device credential ครบแล้ว แต่ child rehearsals บางส่วนยังอ้าง schema ก่อน persistent refresh
credential และยังไม่มี gate เดียวที่รวม migration, security boundary, staff/device audit, regression,
cleanup และการรักษา rollback-safe runtime ไว้เป็นหลักฐานก่อนเดิน roadmap ต่อ

## In Scope

- rerun device registration, Pair/Renew/Rotate/Revoke และ Branch/Station isolation บน durable schema ล่าสุด
- rerun Counter/Kitchen/Pickup workspace, device-type guard และ immediate revoke
- ตรวจ Counter staff login, เปิดกะ, เปลี่ยนกะ, replay guard และ audit ที่ผูก staff/Branch/device
- rerun signed offline authorization, expiry, per-order `needs_review`, revoke timing และ legacy paid queue
- rehearsal legacy/Platform upgrade → downgrade → re-upgrade บนฐานข้อมูลชั่วคราว
- backend regression, frontend type-check/build, temporary database cleanup และ isolated image safety
- บันทึก browser Counter Pair/device-gate evidence ที่ Platform Owner ยืนยันแล้ว

## Database / Ownership

- legacy Identity head สำหรับ gate คือ `p3device0004`
- Platform Identity head คือ `p3platform0007`; schema contract version `5`
- refresh credential ตัวจริงไม่อยู่ใน database/audit; Identity เก็บเฉพาะ keyed hash
- Restaurant operational database ไม่มี device credential และไม่มี migration ใหม่ใน gate นี้
- child rehearsals clone live legacy/Platform/Restaurant แบบแยกฐานและลบอัตโนมัติ
- current-code backend ใช้ image `restaurant-pos-dev-backend:phase3-gate` แยกจาก rollback-safe
  `restaurant-pos-dev-backend:latest`
- runtime คง identity `legacy`, Restaurant service `legacy`, projector disabled

## Out of Scope

- ติดตั้ง APK และ Pair/restart/offline/reconnect บน physical tablet; Platform Owner เลื่อนไปทำภายหลัง
- release signing, Play Store, MDM, hardware attestation และ remote wipe
- production activation, deploy, push หรือเปลี่ยน database system of record
- เปลี่ยนจาก server-issued Device ID ไปใช้ MAC address

## Acceptance Criteria

- [x] legacy/Platform durable device migrations ผ่าน upgrade → downgrade → re-upgrade
- [x] PIN hash/expiry/lockout/single-use, Branch/Station scope และ device audit ผ่าน
- [x] persistent refresh เก็บเฉพาะ hash, renew ได้ และ rotate/revoke ตัด credential เดิมทันที
- [x] Counter ต้องมีทั้ง staff token และ Counter device token จาก Branch เดียวกัน
- [x] Kitchen/Pickup ถูกล็อกตาม device type, Branch/Station และ revoke มีผลทันที
- [x] เปลี่ยนกะปิด shift, ป้องกัน replay และ audit staff/Branch/device/user-agent ครบ
- [x] signed offline authorization ตรวจ expiry/scope ต่อ order และรักษา legacy paid queue
- [x] live fingerprints ไม่เปลี่ยนและฐานข้อมูลชั่วคราวค้าง `0`
- [x] backend 156 tests, frontend type-check และ production/PWA build ผ่าน
- [x] browser Counter Pair/device gate ผ่านจาก visual evidence ของ Platform Owner
- [x] physical tablet/Android UAT ถูกแยกเป็น deferred follow-up ตามคำสั่ง Platform Owner
- [x] main backend ไม่ถูกเปิดและ rollback-safe `latest` image ไม่ถูกเขียนทับ
- [x] worktree commit โดยไม่ push

## Rollback

1. Gate นี้ไม่ mutate live schema/data และไม่เปิด runtime จึง rollback ด้วยการ revert gate commit ได้
2. หากต้องย้อน durable credential ให้ revert Scope 05 แล้ว downgrade legacy
   `p3device0004 → p3device0003` และ Platform `p3platform0007 → p3platform0006`
3. Dedicated workspaces/offline scopes ไม่มี schema ใหม่; user-session routes และ legacy paid queue ยังอยู่
4. production runtime ยังคง legacy defaults จึงไม่ต้อง cut back selector

## Execution Record

- Starting commit: `7d08003`
- Consolidated gate: `P3-PHASE-GATE-06` ผ่านที่ UTC `2026-08-01T07:20:44Z`
- Device pairing matrix: Branch/Station scope, PIN hash/expiry/lockout, single-use, persistent refresh,
  rotation, revoke, last-seen และ audit ผ่าน
- Workspace matrix: Counter staff gate, Kitchen Station scope, Pickup Branch scope, type guard,
  revoke, operational audit, staff handover และ staff/device audit ผ่าน
- Offline matrix: signed expiry, staff/Branch/shift/location, Counter device, per-order review,
  legacy queue preservation และ revoke timing ผ่าน
- Migration heads: legacy `p3device0004`, Platform `p3platform0007`, contract version `5`
- Live fingerprints ก่อน/หลังไม่เปลี่ยน: legacy `6b7c8d9e0f12:1:4:7:120`,
  Platform `p1platform0003:1:1:7:9`, Restaurant `p1restaurant0003:1:4:23:23`
- Backend regression: 156 tests ผ่าน
- Frontend regression: TypeScript type-check และ production/PWA build ผ่าน; มี chunk-size warning เดิม
- Temporary database cleanup: final query พบ gate prefixes ค้าง `0`
- Main backend: หยุดตลอด gate; visual UAT backend แยก container ยังคงทำงาน
- Rollback-safe image: `restaurant-pos-dev-backend:latest` คง ID
  `sha256:578dd5339c9ea6791d075384e4a2b92cd8422738b809cd147fd6e4eb364cc8de`
- Consolidated artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-phase-gate-06-20260801T072044Z/manifest.txt`
- Pairing artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-device-pairing-01-20260801T072044Z/manifest.txt`
- Workspace artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-dedicated-workspaces-02-20260801T072102Z/manifest.txt`
- Offline artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-offline-authorization-03-20260801T072114Z/manifest.txt`
- Physical tablet/APK UAT: deferred by Platform Owner; ไม่เป็น blocker ของ implementation gate นี้
- Production activation: `false`; ไม่มี deploy และไม่มี push
