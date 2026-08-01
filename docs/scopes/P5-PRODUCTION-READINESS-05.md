# P5-PRODUCTION-READINESS-05

## สถานะ

`automated_gate_and_draft_pr_ci_passed` — non-device production readiness, fresh dependency audits และ Draft PR CI ผ่านแล้ว; physical-device UAT และ owner sign-offs ยัง pending โดยยังไม่ activate production, ไม่ migrate ฐาน live, ไม่สร้าง Platform Owner บนฐาน live และไม่เริ่ม Phase 6

## ปัญหาที่แก้

Gate ก่อนหน้านี้พิสูจน์ business chain, security baseline, role/scope, Retail compatibility และ restore แล้ว แต่หลักฐาน browser viewport, load/reconnect/idempotency, ชุดเอกสารส่งมอบ operator, แบบฟอร์ม device UAT และ security-owner decision ยังไม่รวมเป็น gate เดียวที่ทำซ้ำได้

## In scope

- แก้ CI shell syntax validation ให้เลือก parser จาก shebang ของแต่ละไฟล์
- standalone Chromium UAT ที่ mobile/tablet viewport สำหรับ public menu, table map, kitchen, checkout และ central report
- ตรวจ page error, console error, HTTP 5xx, responsive overflow และเก็บ screenshot
- isolated 100-order offline sync, reconnect และ lost-acknowledgement replay พร้อมตรวจ idempotency ในฐานข้อมูล
- production readiness workbook, physical-device checklist, operator/incident drill และ security risk-decision form
- Draft PR, repository gates และ CI evidence

## Out of scope

- physical device, camera, printer, kiosk, LTE/Wi-Fi handoff และ local-network UAT ก่อนอุปกรณ์มาถึง
- owner/security/platform sign-off แทนผู้รับผิดชอบ
- production deploy, DNS/TLS activation, live migration, live secret/credential creation หรือ live database mutation
- Phase 6 Takeaway implementation หรือ Retail Phase 7 development

## Acceptance criteria

- [x] isolated backend regression และ full QR-to-ERP API UAT ผ่าน
- [x] standalone Chromium mobile/tablet flow ผ่านโดยไม่มี page error, console error หรือ HTTP 5xx
- [x] offline sync 100 orders และ replay หลัง lost acknowledgement ไม่สร้างข้อมูลซ้ำใน sale/payment/session/outbox/journal/stock
- [x] frontend type-check/build, documentation validator และ repository safety ผ่าน
- [x] backend audit ไม่มี known vulnerability และ frontend audit ไม่มี finding นอก reviewed exceptions เดิม
- [x] Draft PR CI ผ่าน
- [x] artifact manifest ระบุ physical/device และ owner sign-offs เป็น pending และ production/Phase 6 เป็น false

## คำสั่ง gate

```sh
P5_READINESS_ADMIN_PASSWORD='use-a-unique-test-secret' \
  ./scripts/rehearse-phase5-readiness.sh --yes
```

Compose project ต้องขึ้นต้น `restaurant-p5-uat-readiness`; gate จะลบเฉพาะ isolated volumes ของชื่อนั้นและเก็บ artifact ภายใต้ `/private/tmp/restaurant-p5-artifacts/`

## Rollback

- revert commit ของ scope นี้หาก CI หรือ review ไม่ผ่าน
- ไม่มี schema migration และไม่มี production/live data change ให้ rollback
- Playwright dependency และไฟล์ทดสอบถูกแยกจาก production runtime; production frontend image ยังคงเป็น nginx/static assets

## Evidence

```text
validated_change_commit: b60ff8b36f100d9080b2a871a5493102439b81a7
draft_pr: https://github.com/chaiyanutaiagent/restaurant/pull/2
ci_push_run: https://github.com/chaiyanutaiagent/restaurant/actions/runs/30708414972
ci_pull_request_run: https://github.com/chaiyanutaiagent/restaurant/actions/runs/30708416232
artifact_manifest: /private/tmp/restaurant-p5-artifacts/p5-production-readiness-05-20260801T162909Z/manifest.txt
physical_device_uat: pending
security_owner_decision: pending
platform_owner_completion_signoff: pending
production_activated: false
phase6_started: false
```
