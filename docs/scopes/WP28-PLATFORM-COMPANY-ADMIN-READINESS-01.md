# WP28 — Platform Console and Company Admin Readiness

วันที่: `2026-09-18`
สถานะ: **engineering_ready — operator MFA/handoff evidence pending**

## ขอบเขตที่ยืนยันแล้ว

- Platform Owner แยก identity/session จาก tenant staff
- login, refresh, logout, lockout, credential version และ revocable session
- MFA enrollment, TOTP/recovery code และ security session management
- Company lifecycle, module flags, plan/billing metadata, usage, operations และ audit
- tenant-approved support access โดยไม่มี silent impersonation
- Company Admin: canonical business URL, branch, user, role, device และ workspace provisioning
- tenant isolation และ rejection ของ session ข้าม Company

## Evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | รวมใน WP27: `386` tests ผ่าน |
| Platform/Company Admin browser regression | `18/18` ผ่าน |
| Production Platform operator | active + superuser; lockout counter `0` |
| Production tenant admin | active + superuser |
| Production audit | มีรายการ audit ใน 24 ชั่วโมงล่าสุด |
| Public/business canonical routing | browser regression ผ่าน |

## Production hard gate ที่ยังไม่สมมติผล

Platform operator ปัจจุบันยังไม่ได้ enroll MFA. ระบบรองรับและ automated test ผ่าน แต่ operator/owner
ต้องเปิดหน้า Platform Security ด้วย authenticator ของตนเอง เก็บ recovery codes ในที่ปลอดภัย และทดสอบ
login/logout/recovery จริงก่อนถือว่า WP28 ผ่าน external exit

## Operator handoff checklist

- [ ] owner เปิด MFA และเก็บ recovery codes นอกเครื่องใช้งาน
- [ ] login ใหม่ด้วย MFA สำเร็จ
- [ ] revoke session เก่าที่ไม่ใช้งาน
- [ ] ทดสอบ recovery code หนึ่งครั้งและออกชุดใหม่เมื่อจำเป็น
- [ ] ระบุ primary/backup operator และ incident contact
- [ ] ตรวจ module activation และ billing/support action พร้อม Audit Log
- [ ] owner ลงชื่อและเวลา

## Decision

Engineering สามารถเดิน WP29 ต่อได้โดยไม่เปิดสิทธิ์เพิ่ม. WP35 ห้ามให้ final `go` หาก checklist ด้านบนยังไม่ครบ
