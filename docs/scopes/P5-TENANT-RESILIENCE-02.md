# Scope ID: P5-TENANT-RESILIENCE-02

สถานะ: **Verified — isolated export/backup/restore/monitoring gate passed**

Phase: **Phase 5 — Platform Onboarding และ Go-live**

## Outcome

- เพิ่ม tenant export จาก Platform Console/API และ operator CLI โดยตาม ownership ผ่าน `company_id`
  หรือ foreign-key parent chain จึงรวมตารางลูก เช่น order items, recipe ingredients และ role permissions
- export แทนค่า password, hash, PIN, OTP, token, API key และ secret ด้วย `[REDACTED]`
  ก่อนสร้าง canonical `content_sha256`
- ทุก Platform API export ต้องระบุเหตุผล และบันทึก `platform.company.export` พร้อม operator,
  checksum, จำนวน boundary/table/row และจำนวนค่าที่ถูก redact
- เพิ่ม backup ของ Legacy, Platform และ Restaurant เป็น dump แยก พร้อม SHA-256 และ tenant export evidence
- เพิ่ม isolated restore drill ที่สร้างเฉพาะ database prefix `restaurant_p5_resilience_*`, restore ทั้งสาม boundary,
  export tenant ซ้ำ และยืนยัน content checksum ก่อนลบฐาน drill
- เพิ่ม production resilience monitor สำหรับ readiness, reference projector failures, disk threshold,
  backup freshness/integrity และ optional webhook alert
- สร้าง incident/recovery evidence ที่บันทึก RTO, source/restored checksum และยืนยันว่า live source ไม่ถูกแก้

## Tenant export

Platform Owner ใช้ `POST /api/v1/platform/companies/:companyId/export` พร้อม body:

```json
{"reason":"Customer data portability request"}
```

หรือใช้ CLI ซึ่งอ่านทั้งสาม configured boundary:

```bash
scripts/export-tenant.sh \
  --company-id COMPANY_UUID \
  --reason "Customer data portability request"
```

JSON artifact ยังมีข้อมูลธุรกิจและข้อมูลส่วนบุคคล จึงต้องเก็บเป็นไฟล์สิทธิ์จำกัด แม้ credential material
จะถูก redact แล้ว รูปภาพ/upload binary ไม่ถูกฝังใน tenant export; production full backup ยังคงรับผิดชอบ
uploads และ Redis operational state แยกต่างหาก

## Backup and isolated restore drill

```bash
scripts/backup-tenant-boundaries.sh \
  --company-id COMPANY_UUID \
  --reason "Scheduled tenant resilience backup"

scripts/restore-tenant-boundaries-drill.sh --yes \
  backups/p5-tenant-boundaries-YYYYMMDDTHHMMSSZ
```

Backup นี้ตั้งใจพิสูจน์ durable PostgreSQL data ข้าม Legacy/Platform/Restaurant และ tenant checksum;
ไม่แทน `scripts/backup-production.sh` ซึ่งรวม uploads/Redis สำหรับ full deployment recovery

## Monitoring and alert delivery

รันจาก scheduler/monitoring host หลังตั้งค่า production base URL และ backup root:

```bash
RESILIENCE_BASE_URL=https://restaurant.example.com \
RESILIENCE_BACKUP_ROOT=/secure/backups \
RESILIENCE_ALERT_WEBHOOK_URL=https://alerts.example.net/hooks/restaurant \
RESILIENCE_EVIDENCE_FILE=/var/log/restaurant/resilience-latest.json \
scripts/monitor-production-resilience.sh
```

ค่า default: backup อายุไม่เกิน `26` ชั่วโมง, disk ต่ำกว่า `80%`, reference projector failed/loop error
ต้องเป็น `0` ปรับด้วย `RESILIENCE_MAX_BACKUP_AGE_HOURS`, `RESILIENCE_MAX_DISK_PERCENT`,
`RESILIENCE_MAX_PROJECTOR_FAILED_EVENTS` และ `RESILIENCE_MAX_PROJECTOR_LOOP_ERRORS`

หาก production policy บังคับ alert delivery ให้ตั้ง `RESILIENCE_REQUIRE_ALERT_WEBHOOK=1`; script จะ fail
เมื่อไม่ได้กำหนด webhook และจะ exit non-zero เมื่อ check ใดเป็น critical

## Safety contract

- Backup/export อ่าน source เท่านั้น
- Restore drill ต้องผ่าน `--yes` และสร้าง/ลบได้เฉพาะชื่อ database prefix ของ scope นี้
- ห้ามใช้ restore drill แทน production restore command
- ห้าม log หรือเก็บ credential material ใน export/audit/recovery evidence
- ห้าม migrate/deploy production หรือสร้าง Platform Owner บนฐาน live จาก scope นี้

## Verification

รัน:

```bash
scripts/rehearse-phase5-tenant-resilience.sh --yes
```

ผลวันที่ 1 สิงหาคม 2026:

- Legacy, Platform และ Restaurant upgrade → downgrade → re-upgrade ผ่านในฐาน isolated
- backend unit regression `185` tests และ Platform tenant API smoke ผ่าน รวม export/audit/redaction
- frontend type-check และ production build ผ่าน พร้อม Platform Console download flow
- three-boundary backup SHA-256 ผ่าน และ tenant content checksum ก่อน/หลัง isolated restore ตรงกัน
- incident recovery drill ใช้เวลา `5` วินาทีใน local environment และบันทึก recovery evidence
- resilience monitor ผ่าน healthy path และสร้าง critical-path evidence/exit non-zero ตาม threshold
- live fingerprints และ `restaurant-pos-dev-backend:latest` ไม่เปลี่ยน; temporary databases ค้าง `0`
- Artifact: `/private/tmp/restaurant-p5-artifacts/p5-resilience-gate-02-20260801T131051Z/manifest.txt`

## Rollback

Scope นี้ไม่มี schema migration: revert API/UI/operator tooling ได้โดยไม่ downgrade database
Artifact ที่สร้างแล้วมีข้อมูล tenant และต้องจัดเก็บ/ทำลายตาม retention policy; การ revert code ไม่ได้ลบ artifact
อัตโนมัติ
