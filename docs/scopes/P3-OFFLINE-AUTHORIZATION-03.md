# Scope ID: P3-OFFLINE-AUTHORIZATION-03

สถานะ: **Automated verification complete — browser/device UAT pending**
Phase: **Phase 3 — Dedicated Counter, Kitchen และ Device Pairing**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Restaurant paid-order outbox มี idempotency และ reconnect อยู่แล้ว แต่ cached user session ยังไม่มี
offline-authorization expiry และ outbox ที่สร้างจาก dedicated Counter ยังไม่ผูกกับ device registry
จึงต้องปิดช่องก่อน tablet pilot โดยไม่ทำลายยอดที่รับเงินจริงและค้างใน outbox รุ่นก่อน

## In Scope

- signed offline-sale authorization ที่มี configurable expiry (default 12 ชั่วโมง)
- ผูก user, Company, Branch, shift, location, Brand และ optional Counter device
- `/counter/orders` ต้องผ่านทั้ง Counter device guard และ `fb.order.create` staff guard
- current frontend ปฏิเสธการรับ payment ใหม่เมื่อ lease หาย, หมดอายุ หรือเป็นคนละ Counter
- sync ตรวจ lease ต่อ order และส่ง conflict ไป `needs_review` โดยไม่ล้มทั้ง batch
- device revoke: รักษายอดที่สร้างก่อน revoke และปฏิเสธยอดที่อ้างว่าสร้างหลัง revoke
- rollout compatibility สำหรับ durable outbox ที่สร้างก่อน policy version 1
- isolated API gate, backend regression และ frontend type/build

## Database / Ownership

- ไม่มี migration ใหม่; authorization เป็น signed short-lived claim และไม่เก็บ secret เพิ่มใน DB
- device live/revoke evidence อ่านจาก Identity-owned registry
- paid-order outbox ยังอยู่ IndexedDB และ canonical order ยังอยู่ Restaurant service database
- default runtime คง identity `legacy`, Restaurant service `legacy`, projector disabled

## Out of Scope

- เชื่อถือ client clock แบบ hardware-attested หรือ secure enclave
- background sync ขณะ app ถูก terminate, Room/SQLite native worker
- secure native keystore, printer UAT, release signing และ production activation
- ลบ legacy outbox compatibility ก่อน rollout window จบ

## Acceptance Criteria

- [x] menu bootstrap ออก signed lease ที่มี policy/issued/expiry และ server-owned scope
- [x] Counter route ส่ง device credential แยกจาก user credential และ lease ผูก device ID
- [x] Kitchen/Pickup device ใช้ออก Counter lease ไม่ได้
- [x] frontend block payment ใหม่เมื่อ lease หาย/หมดอายุ/ไม่ตรง Counter
- [x] tampered user/Branch/shift/location/Brand/device ถูกส่ง `needs_review` ราย order
- [x] valid pre-revoke paid order ไม่หาย และ post-revoke order ถูกปฏิเสธ
- [x] outbox รุ่นก่อน policy ยัง replay ได้ระหว่าง rollout
- [x] isolated API gate ผ่านและ live fingerprints ไม่เปลี่ยน
- [x] backend regression, frontend type/build ผ่าน
- [ ] physical/browser offline → reload → reconnect UAT ผ่าน
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. revert source commit และเอา lease fields ออกจาก menu/outbox payload
2. backend รองรับ legacy rows อยู่แล้ว จึงไม่ต้องแก้ IndexedDB หรือทิ้ง paid order
3. ไม่มี schema downgrade
4. dedicated workspace/device registry ของ Scope 01–02 ยังทำงานได้

## Execution Record

- Starting commit: `560da7a`
- Runtime: identity `legacy`, Restaurant service `legacy`, projector disabled
- Offline policy version: `1`; default lease `12` ชั่วโมง
- API gate: signed expiry, staff/Branch/shift/location, Counter device, per-order review,
  legacy compatibility และ revoke timing ผ่าน
- Backend regression: 152 tests ผ่าน
- Frontend: TypeScript type-check และ production build ผ่าน
- Live fingerprints ก่อน/หลังไม่เปลี่ยน: legacy `6b7c8d9e0f12:1:4:7:120`,
  Platform `p1platform0003:1:1:7:9`, Restaurant `p1restaurant0003:1:4:23:23`
- Rehearsal artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-offline-authorization-03-20260801T034107Z/manifest.txt`
- Temporary database cleanup: final query พบฐาน prefix `restaurant_p3_offline_` ค้าง `0`
- Physical/browser UAT: pending เพราะ Browser instance ไม่พร้อมใน session นี้
- Commit: บันทึก automated-verification checkpoint ใน Git history โดยไม่ push;
  physical/browser UAT จะตามเป็น evidence/fix commit เมื่อ Browser/device พร้อม
