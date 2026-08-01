# Scope ID: P3-DEVICE-PAIRING-01

สถานะ: **Verified — device identity and pairing foundation complete**
Phase: **Phase 3 — Dedicated Counter, Kitchen และ Device Pairing**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Counter, Kitchen และ Pickup pages มี route/UI เดิม แต่ยังอาศัย user access token จึงไม่สามารถติดตั้ง
tablet ประจำ Branch/Station โดยไม่ใช้บัญชีพนักงานหรือ Company Owner, ไม่มี server-side device registry,
pairing credential, revoke enforcement และ last-seen evidence ตาม Phase 3 roadmap

## In Scope

- Identity-owned device registry สำหรับ `counter`, `kitchen` และ `pickup`
- Device code และ one-time pairing PIN/QR ที่หมดอายุและมี failed-attempt lockout
- ผูก Company/Restaurant Branch จาก server และบังคับ Kitchen Station จาก Branch settings
- device access token ที่มี credential version และตรวจ live registry ทุก request
- revoke และ pairing-code rotation ที่ทำให้ token เดิมใช้ต่อไม่ได้ทันที
- device self-context/heartbeat และ last-seen timestamp
- permission สำหรับดู/จัดการ device ใน Company Owner, Brand Manager และ Branch Manager presets
- audit create, pairing-code rotation, successful pair และ revoke
- legacy/Platform migrations, API/unit tests และ isolated rehearsal

## Database / Ownership

- `device_registrations` เป็น Identity-owned table ใน legacy และ Platform เท่านั้น
- Branch/Brand/Station context ถูก resolve ฝั่ง server; client เลือก context ใน token เองไม่ได้
- Restaurant Branch settings ใช้ตรวจ canonical Kitchen Station แต่ไม่เก็บ device credential
- default runtime คง identity `legacy`, Restaurant service `legacy`, projector disabled

## Out of Scope

- Dedicated Counter/Kitchen/Pickup device endpoints และ route guards ซึ่งทำใน Scope ถัดไป
- offline order queue/reconnect gate และ Samsung Galaxy Tab A11 visual UAT
- native mobile app, MDM, remote notification หรือ production activation
- เปลี่ยน system of record หรือ runtime database selector

## Acceptance Criteria

- [x] Manager ที่มี scope เข้าถึงได้เฉพาะ device ใน Company/Branch context ของตน
- [x] Kitchen device จับคู่ได้เฉพาะ Station ที่มีใน Branch settings
- [x] pairing PIN ถูก hash, หมดอายุ, ใช้ซ้ำไม่ได้ และผิดครบ limit ถูก lock
- [x] QR payload ไม่มี authority เพิ่มจาก one-time PIN และ server-resolved device record
- [x] Tablet pair และอ่าน device context ได้โดยไม่ใช้ User/Company Owner credential
- [x] token mismatch, credential rotation และ revoked device ถูกปฏิเสธทุก request
- [x] last-seen และ audit actor/Branch/reason ถูกบันทึก
- [x] device credential ไม่มีใน Restaurant operational database
- [x] legacy/Platform upgrade → downgrade → re-upgrade ผ่านโดย live fingerprints ไม่เปลี่ยน
- [x] backend unit/API regression ผ่าน
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. ปิด device-auth route และ revert source commit ของ Scope นี้
2. downgrade Platform และ legacy migrations หลังยืนยันว่าไม่มี device ที่ต้องรักษา credential
3. Dedicated pages เดิมยังใช้ user session ตามเดิมจนกว่า Scope ถัดไปผ่าน gate
4. runtime flags คง legacy defaults จึงไม่ต้อง cut back database selector

## Execution Record

- Starting commit: `b63052e`
- Starting heads: legacy `p2approval0002` บน rehearsal clone จาก live `6b7c8d9e0f12`,
  Platform `p2platform0005` บน clone จาก live `p1platform0003`, Restaurant live `p1restaurant0003`
- Starting runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Current role preset policy: `2026-08-01.4`; Company Owner, Brand Manager และ Branch Manager
  ได้ `system.device.view/manage` โดย Cashier/Kitchen Staff ไม่ได้สิทธิ์นี้
- Identity schema: legacy `p3device0003`, Platform `p3platform0006`; Platform contract version `4`
- Restaurant schema: ไม่มี `device_registrations` และไม่มี device credential
- API matrix: Branch isolation, canonical Kitchen Station, PIN hash/expiry/lockout, QR scope,
  single-use, row-locked rotation, user-token rejection, device self-context, last-seen และ revoke ผ่าน
- Token enforcement: credential version, Company/Brand/Branch/type/Station และ live registry ถูกตรวจทุก request;
  token ก่อน rotate/revoke ได้ `401`
- Audit: create/rotate/revoke มี Manager actor และ reason; pair มี device event โดยไม่เก็บ PIN/hash
- Migration rehearsal: Legacy/Platform ผ่าน upgrade → downgrade → re-upgrade บนฐานชั่วคราว
- Live fingerprints ก่อน/หลังไม่เปลี่ยน: legacy `6b7c8d9e0f12:1:4:7:120`,
  Platform `p1platform0003:1:1:7:9`, Restaurant `p1restaurant0003:1:4:23:23`
- Backend regression: 147 tests ผ่าน
- Rehearsal artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-device-pairing-01-20260801T030424Z/manifest.txt`
- Temporary database cleanup: final query พบฐาน prefix `restaurant_p3_device_` ค้าง `0`
- Final runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Commit: บันทึกใน Git history ของ Scope ID นี้โดยไม่ push
