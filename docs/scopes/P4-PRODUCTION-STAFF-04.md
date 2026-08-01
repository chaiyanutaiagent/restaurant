# Scope ID: P4-PRODUCTION-STAFF-04

สถานะ: **Verified — production entitlement and Employee-linked assignment complete**

Phase: **Phase 4 — Restaurant ERP Core**

Business type: **restaurant**

Target databases: **Platform Control Plane for feature/staff assignment; Restaurant database for production operations**

## Problem

Central production routes ตรวจ permission แล้วแต่ไม่มี tenant/Brand feature flag จึงเปิดใช้ทันทีสำหรับทุกแบรนด์ที่มี role
ส่วน StaffRoleAssignment อ้างเพียง User ทำให้ผู้จัดการสร้าง assignment ใหม่ให้บัญชีที่ไม่เชื่อมกับ HR Employee ได้
และหน้าตรวจ assignment ไม่แสดงหลักฐาน Employee ที่เกี่ยวข้อง

## In Scope

- เพิ่ม Brand module entitlement `restaurant.central_production` ใน Platform Control Plane
- เพิ่ม Company-admin API สำหรับอ่าน/เปิด/ปิด flag พร้อม audit
- ทุก Brand production read/write route ต้องตรวจ permission, Brand assignment และ feature flag
- feature endpoint แบบ read-only สำหรับ Restaurant shell เพื่อซ่อนเมนู Production เมื่อปิด
- assignment ระดับ Brand/Branch/Station ใหม่ต้องเชื่อม Active HR Employee ของ Company เดียวกัน
- assignment response แสดง employee id/code/name โดยไม่เพิ่ม payroll
- รักษา Company Owner assignment ที่ไม่บังคับ Employee เพื่อรองรับ account เจ้าของกิจการ
- เพิ่ม regression สำหรับ disabled/enabled flag, cross-tenant isolation และ Employee-linked assignment

## Out of Scope

- payroll, salary, attendance หรือการเปลี่ยน HR calculation
- plan billing/automatic entitlement provisioning (Phase 5)
- Takeaway/Retail feature flags
- production runtime cutover และ APK

## Database / Ownership

- Module entitlement และ assignment/Employee identity link อยู่ Platform database
- ProductionBatch/Line และ stock movement อยู่ Restaurant database
- production request ใช้สอง connection แบบ read authorization ก่อน Restaurant transaction; ไม่มี distributed transaction
- ไม่มี SQL FK จาก Restaurant operational data ไป Platform/Retail/Takeaway

## Acceptance

- [x] flag ปิดทำให้ production API ปฏิเสธโดยไม่เขียนข้อมูล
- [x] flag เปิดและ permission/scope ถูกต้องจึงใช้ production API ได้
- [x] Brand อื่นหรือ Company อื่นไม่สามารถอ่าน/แก้ flag ได้
- [x] Brand/Branch/Station assignment ใหม่สำหรับ User ที่ไม่มี Active Employee ถูกปฏิเสธ
- [x] assignment response แสดง Employee link ที่ตรวจสอบย้อนกลับได้
- [x] Company Owner assignment เดิมยังรองรับได้และไม่มี payroll schema ใหม่

## Execution Record

- Production smoke ยืนยัน disabled-by-default, Company-admin enable และ batch start/complete/cancel
- Staff API matrix ผ่าน Company/Brand/Branch/Station, multi-role, revoke audit และ station isolation
- Operational assignment fixture ใช้ Active Employee link จริง; Company Owner scope ยังคงได้รับการยกเว้น
- Legacy/Platform entitlement migrations ผ่าน upgrade → downgrade → re-upgrade
- หลักฐานรวมอยู่ใน `P4-PHASE-GATE-06`

## Rollback

- ปิด feature flag เพื่อหยุด production โดยไม่ลบ batch/stock history
- downgrade ลบเฉพาะ entitlement table/index; assignment schema ไม่มี destructive change
- revert Employee validation คืน behavior เดิมได้โดยข้อมูล assignment เดิมไม่เปลี่ยน
