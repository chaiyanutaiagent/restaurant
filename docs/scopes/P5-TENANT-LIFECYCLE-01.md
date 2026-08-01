# Scope ID: P5-TENANT-LIFECYCLE-01

สถานะ: **Verified — isolated migration/API/security gate passed**

Phase: **Phase 5 — Platform Onboarding และ Go-live**

## Outcome

- เพิ่ม workspace `/platform` แยกจาก Company Owner ตาม Control Plane contract
- เพิ่ม Platform Owner identity และ JWT `platform_access` ซึ่งใช้แทน tenant token ไม่ได้
- Platform Owner สร้าง Company พร้อม Company Owner คนแรกได้จาก UI/API โดยไม่แก้ source code หรือ SQL
- Company Owner ถูกสร้างพร้อม system Role และ Company-scope assignment; password ถูก hash และไม่ถูกส่งกลับใน response/audit
- เพิ่ม onboarding checklist ที่อ่านสถานะจริงตามลำดับ Company → Brand → Branch → Menu → Payment → Staff → Device
- เพิ่ม manual feature flags และ plan limits; ค่า limit `0` หมายถึงไม่จำกัด และ Companies เดิมที่ยังไม่มี Platform profile คง backward-compatible
- บังคับ limit เมื่อสร้าง Brand, Branch, User และ Device และบังคับ Restaurant feature flag กับ authenticated Restaurant routes
- ระงับ Company แล้วเพิ่ม `credential_version`, revoke refresh sessions และล้าง device credentials ทันที
- เปิด Company ใหม่ไม่ทำให้ user/device token รุ่นก่อนกลับมาใช้ได้; user ต้อง login ใหม่และ tablet ต้องจับคู่ใหม่
- ทุก mutation ระดับ Platform ต้องระบุเหตุผลและบันทึก `platform.*` Audit Log

## Platform bootstrap

ไม่มี default Platform credential ใน source หรือ environment template ให้สร้างหรือ rotate Platform Owner ผ่าน command ที่ hash password และเขียนด้วย ORM:

```bash
docker compose run --rm backend \
  python -m app.utils.create_platform_operator \
  --username platform.owner \
  --display-name "Platform Owner"
```

ใช้ `PLATFORM_OPERATOR_PASSWORD` เฉพาะกรณี automation ที่จัดการ secret ให้แล้ว; หากไม่ตั้ง command จะถาม password แบบไม่แสดงบน terminal

## API and routes

- `POST /api/v1/platform/auth/login`
- `GET /api/v1/platform/auth/me`
- `GET|POST /api/v1/platform/companies`
- `GET /api/v1/platform/companies/:companyId`
- `POST /api/v1/platform/companies/:companyId/suspend`
- `POST /api/v1/platform/companies/:companyId/reactivate`
- `PUT /api/v1/platform/companies/:companyId/controls`
- `GET /api/v1/platform/audit`
- `/platform/login`, `/platform/companies`, `/platform/companies/:companyId`, `/platform/audit`

## Data contracts

- Legacy head: `p5tenant0007`
- Platform head: `p5platform0009`
- Restaurant head: `p5restaurant0006`
- Platform-owned tables: `platform_operators`, `platform_tenant_profiles`
- Cross-boundary Company reference เพิ่ม `credential_version`; reference projector ส่งค่านี้ไป Restaurant projection

## Verification

รัน:

```bash
scripts/rehearse-phase5-tenant-lifecycle.sh --yes
```

ผลวันที่ 1 สิงหาคม 2026:

- Legacy, Platform และ Restaurant upgrade → downgrade → re-upgrade ผ่านบน database clone
- Backend unit regression `183` tests ผ่าน
- Platform tenant API smoke ผ่าน create Company/Owner, onboarding, controls, audit, suspend/reactivate
- user access และ device access ถูกปฏิเสธระหว่าง suspend
- old user/device generation ยังถูกปฏิเสธหลัง reactivate; fresh user login ผ่าน
- authenticated Restaurant route ถูกปฏิเสธเมื่อ manual feature flag ปิด
- frontend `type-check` และ production build ผ่าน
- live Legacy/Platform/Restaurant fingerprints และ `restaurant-pos-dev-backend:latest` ไม่เปลี่ยน
- Artifact: `/private/tmp/restaurant-p5-artifacts/p5-tenant-gate-01-20260801T113314Z/manifest.txt`

## Not activated

- ไม่ migrate หรือ deploy production
- ไม่เปลี่ยน runtime cutover
- ไม่สร้าง Platform Owner บนฐาน live
- ไม่เปิด automatic subscription billing
- Scope backup/restore, tenant export, full UAT, production security review และ owner sign-off ยังอยู่ใน Phase 5 scopes ถัดไป

## Rollback

1. หยุด Platform Console/API version นี้
2. Revert implementation commit
3. Downgrade เฉพาะ additive Phase 5 migrations ไป `p4feature0006`, `p4platform0008`, `p4restaurant0005` หากเคย apply ภายหลัง
4. Token รุ่นก่อน Phase 5 ที่ Company ยังอยู่ generation `1` รองรับแบบ backward-compatible; Company ที่เคย suspend ต้องออก session/device credential ใหม่ตาม security policy
