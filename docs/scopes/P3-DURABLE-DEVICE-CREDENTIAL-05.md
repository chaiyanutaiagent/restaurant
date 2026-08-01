# Scope ID: P3-DURABLE-DEVICE-CREDENTIAL-05

สถานะ: **Automated/API/Android build verified — tablet interaction pending**
Phase: **Phase 3 — Dedicated Counter, Kitchen และ Device Pairing**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

Pairing foundation เดิมเก็บ device access token ใน browser `localStorage` และ token มีอายุ 30 วัน
จึงทนต่อการปิด/เปิดทั่วไปแต่ยังไม่ใช่ “Pair ครั้งเดียว” อย่างแท้จริง การใช้ MAC address แก้ไม่ได้เพราะ
Browser/PWA อ่าน MAC ไม่ได้และ Android อาจสุ่ม MAC ตามเครือข่าย

## In Scope

- ใช้ server-issued Device ID/Code และ credential version เดิม ไม่ใช้ MAC address
- ออก persistent refresh credential แบบสุ่มเมื่อ Pair สำเร็จ และเก็บฝั่ง Identity เฉพาะ keyed hash
- เพิ่ม `POST /api/v1/device-auth/renew` เพื่อออก access token ใหม่โดยไม่ Pair ซ้ำ
- เก็บ device session ใน Android AES-GCM secure storage ที่ใช้ key จาก Android Keystore
- hydrate credential ก่อน device route guard และ renew อัตโนมัติเมื่อเปิด workspace
- รักษา paired state เมื่อเครือข่ายขาด; หาก access หมดอายุให้รอเชื่อมต่อแทนการบังคับ Pair ใหม่
- rotate pairing code และ revoke ต้องล้าง refresh credential และตัด access/refresh เดิมทันที
- browser ใช้ origin-persistent storage เป็น fallback พร้อมระบุข้อจำกัดชัดเจน

## Database / Ownership

- เพิ่ม `device_registrations.refresh_credential_hash` และ `refresh_credential_issued_at` ใน Identity-owned
  legacy/Platform เท่านั้น
- refresh credential ตัวจริงไม่ลงฐานข้อมูล, audit หรือ Restaurant operational database
- legacy head `p3device0004`; Platform head `p3platform0007`, contract version `5`
- runtime default ยังคง identity `legacy`, Restaurant service `legacy`, projector disabled

## Security Rules

- refresh token เป็น random secret ความยาวสูงและมี Device ID สำหรับ lookup เท่านั้น
- server hash ด้วย HMAC-SHA-256 และเปรียบเทียบแบบ constant time
- renewal โหลด Company/Brand/Branch/type/Station จาก live registry ใหม่ทุกครั้ง
- Manager rotate/revoke เป็น authoritative kill switch; MAC หรือ client context ไม่มีอำนาจ
- Android manifest ปิด backup จึงไม่ย้าย encrypted credential ข้ามเครื่อง

## Out of Scope

- MDM, hardware attestation, biometric app unlock และ remote wipe
- รักษา Pair หลังถอนการติดตั้ง, clear app data หรือ clear browser site data
- production activation หรือเปลี่ยน runtime database selector

## Acceptance Criteria

- [x] Pair ครั้งเดียวแล้ว access token renew อัตโนมัติข้าม app restart
- [x] server เก็บ refresh credential เฉพาะ hash และไม่ใส่ secret ใน audit
- [x] Android เก็บ session ด้วย AES-GCM/Keystore-backed secure storage
- [x] browser fallback คง session ข้าม refresh และ browser restart ตาม origin storage
- [x] network outage ไม่ล้าง Pair; expired access แสดง reconnect gate
- [x] rotate ทำให้ access และ refresh เดิมได้ HTTP 401
- [x] revoke ทำให้ access และ refresh เดิมได้ HTTP 401
- [x] legacy/Platform upgrade → downgrade → re-upgrade ผ่าน
- [x] backend regression 156 tests, frontend type/build และ Android debug APK ผ่าน
- [x] live database fingerprints ไม่เปลี่ยน
- [ ] ยืนยัน Pair → reload/ปิดเปิดหน้า → เข้า Workspace โดยไม่ Pair ซ้ำบน tablet
- [x] worktree commit โดยไม่ push

## Rollback

1. revert source commit ของ Scope นี้
2. downgrade legacy `p3device0004 → p3device0003`
3. downgrade Platform `p3platform0007 → p3platform0006` ซึ่งคืน contract `5 → 4`
4. Tablet รุ่นเดิมยังใช้ access token ที่ยังไม่หมดอายุ; หลังหมดอายุต้อง Pair ใหม่ตามพฤติกรรมก่อน Scope นี้

## Execution Record

- Starting commit: `3be4f26`
- UAT legacy clone: `restaurant_p3_device_refresh_20260801_1215`
- UAT Platform clone: `restaurant_p3_device_refresh_platform_20260801_1215`
- Migration rehearsal: upgrade → downgrade → re-upgrade ผ่าน; downgrade ลบสองคอลัมน์และคืน Platform contract `4`
- API matrix: Pair, hashed persistent refresh, renew, invalid refresh, rotate invalidation และ revoke invalidation ผ่าน
- Backend regression: 156 tests ผ่าน
- Frontend: TypeScript type-check และ production/PWA build ผ่าน; asset `assets/index-4Qjdl1tJ.js`
- Production dependency audit: แก้ PostCSS high advisory โดยไม่ force; เหลือ React Router 2 moderate
  ซึ่งต้องอัปเกรด major version จึงแยกออกจาก Scope นี้
- Android: Capacitor sync พบ secure-storage plugin และ `assembleDebug` ผ่านด้วย JDK 21
- APK: `frontend/android/app/build/outputs/apk/debug/app-debug.apk`
- APK SHA-256: `83e4e86cece23175de58999ec70ecb8a52f06ae4c0bd082794a2fd1e8b1cf18e`
- Native storage: `@aparajita/capacitor-secure-storage@7.1.6`; Android AES-GCM + Keystore
- Existing device ที่ Pair ด้วยรุ่นก่อน Scope นี้ไม่มี refresh credential จึงต้อง Pair migration หนึ่งครั้ง
  เมื่อ access เดิมหมดอายุ; หลังจากนั้นเป็น durable pairing
- Tablet visual device: `cc04b624-634e-44cb-b1e3-e5ce8d329b37` / `C-EF9H5QD6NR`
- Live fingerprints ไม่เปลี่ยน: legacy `6b7c8d9e0f12:1:4:7:120`, Platform
  `p1platform0003:1:1:7:9`, Restaurant `p1restaurant0003:1:4:23:23`
- Evidence artifact:
  `/private/tmp/restaurant-p3-artifacts/p3-durable-device-credential-05-20260801T052800Z/manifest.txt`
- Tablet interaction: pending on Chrome opened at `localhost:8081`
