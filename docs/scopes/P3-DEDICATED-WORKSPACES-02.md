# Scope ID: P3-DEDICATED-WORKSPACES-02

สถานะ: **Automated verification complete — browser visual gate pending**
Phase: **Phase 3 — Dedicated Counter, Kitchen และ Device Pairing**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Device registry และ pairing มีแล้ว แต่ fullscreen Counter, Kitchen และ Pickup routes เดิมยังใช้ user token
หรือไม่มี device guard ทำให้ tablet ประจำร้านยังไม่สามารถล็อก Company/Branch/Station จาก registry ฝั่ง server ได้

## In Scope

- แยก persisted device session และ HTTP client ออกจาก user session
- `/device/pair` รองรับ Company ID, Device Code, one-time PIN และ QR query
- `/devices` สำหรับ Manager ดู/สร้าง/rotate/revoke อุปกรณ์ตาม scope
- `/counter`, `/kitchen`, `/pickup` เป็น dedicated fullscreen device routes
- device-only backend endpoints ที่บังคับ type, Company, Branch และ Kitchen Station ฝั่ง server
- Kitchen progress `pending → cooking → done` และ Pickup serve พร้อม device audit
- Counter physical-device gate และ staff-login handoff โดยไม่ให้ device แอบอ้างเป็น cashier
- คง user-session routes `/restaurant/kitchen` และ `/restaurant/pickup` ไว้
- isolated API gate, frontend type/build และ browser visual verification

## Database / Ownership

- ไม่มี migration ใหม่; credential ยังอยู่ Identity-owned `device_registrations` เท่านั้น
- Kitchen/Pickup operational data และ device action audit อยู่ Restaurant service database
- device audit ใช้ `user_id = null` และเก็บ `device_id`, code, Branch, Station ใน evidence
- default runtime คง identity `legacy`, Restaurant service `legacy`, projector disabled

## Out of Scope

- ทำรายการขายด้วย device identity; Counter ต้องมี staff user/shift เพื่อรักษา audit
- offline order queue/reconnect conflict gate
- native MDM, remote lock/wipe หรือ production activation
- เปลี่ยน system of record หรือ database selector

## Acceptance Criteria

- [x] device token แยกจาก user token และ user token ใช้ device endpoint ไม่ได้
- [x] device type เปิดได้เฉพาะ workspace ของตัวเอง
- [x] Counter bootstrap ล็อก Branch และบังคับ staff login ก่อนเข้า POS
- [x] Kitchen list/update ถูกล็อก Branch/Station โดยไม่รับ scope จาก client
- [x] Pickup queue/serve ถูกล็อก Branch โดยไม่รับ scope จาก client
- [x] rotate/revoke ทำให้ workspace token เดิมใช้ไม่ได้ทันที
- [x] Manager UI สร้าง pairing QR/PIN, rotate และ revoke ได้ตาม permission
- [x] existing Restaurant user routes ยังทำงานแบบเดิม
- [x] isolated API gate ผ่านและ live fingerprints ไม่เปลี่ยน
- [x] backend regression, frontend type/build ผ่าน
- [ ] browser visual/route-guard gate ผ่าน
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. ปิด `device_workspaces` router และ revert source commit ของ Scope นี้
2. เอา dedicated routes และ device store ออกจาก frontend; user-session routes เดิมยังอยู่
3. ไม่มี schema downgrade เพราะ Scope นี้ไม่มี migration ใหม่
4. device registry ของ Scope 01 และ runtime legacy defaults ไม่ได้รับผลกระทบ

## Execution Record

- Starting commit: `b95a554`
- Starting runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Schema heads ที่ต้องใช้: legacy `p3device0003`, Platform `p3platform0006`, Restaurant `p1restaurant0003`
- API gate: Counter staff gate, Kitchen Branch/Station isolation, Pickup Branch isolation,
  device-type mismatch, immediate revoke และ operational audit ผ่าน
- Backend regression: 149 tests ผ่าน
- Frontend: TypeScript type-check และ production build ผ่าน; PWA artifacts สร้างสำเร็จ
- Live fingerprints ก่อน/หลังไม่เปลี่ยน: legacy `6b7c8d9e0f12:1:4:7:120`,
  Platform `p1platform0003:1:1:7:9`, Restaurant `p1restaurant0003:1:4:23:23`
- Rehearsal artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-dedicated-workspaces-02-20260801T032651Z/manifest.txt`
- Temporary database cleanup: final query พบฐาน prefix `restaurant_p3_workspace_` ค้าง `0`
- Browser skill initialized แต่ session นี้ไม่มี browser instance (`agent.browsers.list()` ว่าง)
  จึงไม่ใช้ standalone automation แทนและเก็บ visual gate ไว้ทำเมื่อ Browser พร้อม
- Commit: บันทึก automated-verification checkpoint ใน Git history โดยไม่ push;
  browser visual gate จะตามเป็น evidence/fix commit เมื่อ Browser instance พร้อม
