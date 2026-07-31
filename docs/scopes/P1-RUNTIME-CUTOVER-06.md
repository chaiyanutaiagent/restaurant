# Scope ID: P1-RUNTIME-CUTOVER-06

สถานะ: **Verified — canary complete; final runtime rolled back to legacy**
Phase: **Phase 1 — Tenant, Brand และ Branch Foundation**
วันที่เริ่ม: 1 สิงหาคม 2026
ผู้อนุมัติให้ดำเนินการ: Platform Owner

## Problem

`P1-REFERENCE-PROJECTION-05` พิสูจน์ Platform outbox และ Restaurant reference projector แล้ว
แต่ API runtime ยังอ่าน/เขียน identity ทั้งหมดผ่าน legacy database จึงยังไม่ได้พิสูจน์ว่า request จริง
สามารถ commit Platform transaction, ส่ง reference event และย้อน route กลับ legacy ได้

Branch create/update ยังไม่เหมาะเป็น canary แรก เพราะ response และ setup flow ใช้ BranchSettings,
stock location และ operational context ร่วมกัน ส่วน authentication flow ใช้เฉพาะ Platform-owned
Company/User/Role/Permission/UserBranch/RefreshToken/Audit tables จึงเป็น bounded slice ที่เล็กกว่า

## Runtime Slice

- Canary routes: `/api/v1/auth/login`, `/refresh`, `/logout`, `/me`, `/switch-branch`,
  `/permissions` และ identity validation dependency ของ authenticated requests
- Server-owned switch: `IDENTITY_DATABASE=legacy|platform_core`
- Default/rollback value: `legacy`
- Canary value: `platform_core`
- Projector switch: `REFERENCE_PROJECTOR_ENABLED=false|true`
- Runtime Restaurant operational sessions ยังใช้ legacy `DATABASE_URL`

## In Scope

- เพิ่ม server-owned identity session factory และ dependency
- route AuthService และ current-user validation ไปตาม `IDENTITY_DATABASE`
- enqueue User reference event ใน Platform transaction เดียวกับ `last_login_at`, refresh token และ
  login audit commit
- เพิ่ม in-process projector loop ที่ใช้ existing `FOR UPDATE SKIP LOCKED` เพื่อรองรับหลาย replica
- startup guard ห้ามเปิด Platform identity เมื่อ URL ไม่แยกจริงหรือ projector ปิดอยู่
- แสดง active identity source และ projector mode ใน auth metadata/readiness payload
- UAT legacy baseline → Platform canary → projection parity → legacy rollback
- พิสูจน์ว่า Platform-issued refresh token ไม่เขียน legacy และ rollback บังคับ re-login ได้
- regression และ Restaurant smoke หลัง rollback

## Consistency Contract

1. Login อ่าน User/assignment/permission จาก active identity database เท่านั้น
2. เมื่อ active source เป็น Platform, `last_login_at`, refresh token, audit และ User outbox event commit
   ใน Platform transaction เดียวกัน
3. Projector apply User current state ไป Restaurant หลัง Platform commit; ไม่มี distributed transaction
4. Access token เป็น signed JWT และยัง validate กับ active identity source ทุก request
5. เมื่อ rollback เป็น legacy, Platform-issued refresh token ใช้ต่อไม่ได้และผู้ใช้ต้อง login ใหม่
6. Operational routers ยังใช้ legacy database จนกว่าจะผ่าน Restaurant workflow cutover แยก scope

## Out of Scope

- Branch create/update cutover
- User/Role/assignment administration write cutover
- Restaurant operational router cutover
- copy Platform refresh token ไป legacy หรือ Restaurant
- shared refresh-token session ระหว่าง rollback databases
- production deploy, production flag activation หรือ push
- Retail/Takeaway runtime routing

## Acceptance Criteria

- [x] default `IDENTITY_DATABASE=legacy` รักษา backward compatibility
- [x] Platform mode start ไม่ได้หาก Platform URL fallback ไป legacy
- [x] Platform mode start ไม่ได้หาก projector ปิด
- [x] Platform login/refresh/logout/switch-branch ใช้ Platform session
- [x] authenticated dependency validate User/branch context จาก active identity source
- [x] login User event commit ใน Platform transaction เดียวกับ identity writes
- [x] worker process event และ Restaurant User projection parity ผ่าน
- [x] Platform refresh token ไม่ปรากฏใน legacy database
- [x] rollback เป็น legacy สำเร็จ; access validation ยังทำงานและ Platform refresh ต้อง re-login
- [x] readiness แสดง active mode และทุก dependency เป็น `ok`
- [x] backend regression และ Restaurant functional/permission smoke ผ่าน
- [x] worktree commit แล้วโดยไม่ push

## Rollback

1. ตั้ง `IDENTITY_DATABASE=legacy`
2. ตั้ง `REFERENCE_PROJECTOR_ENABLED=false` หากไม่มี Platform writer อื่น
3. restart backend และตรวจ `/health/ready`
4. แจ้งผู้ใช้ที่มี Platform refresh token ให้ login ใหม่; access token เดิมยังผ่านได้จนหมดอายุหาก
   User ยังคง active ใน legacy
5. ห้าม copy refresh token หรือ token hash ข้าม database
6. Platform outbox และ audit คงไว้เป็นหลักฐาน canary; ไม่ต้อง restore legacy

## Execution Record

- Starting commit: `cb533eb`
- Starting identity source: legacy
- Starting Platform head: `p1platform0003`
- Starting Restaurant head: `p1restaurant0003`
- Starting legacy head: `6b7c8d9e0f12`
- Final rehearsal: `/private/tmp/restaurant-cutover06-final-rehearsal-rerun/p1-runtime-cutover-06-20260731T181212Z`
- Pre-canary legacy dump SHA-256: `e8508c35422cdbb08cd4a360bb6eb3f50cf0bb7e7ac367ff2c58598d7632d77e`
- Pre-canary Platform dump SHA-256: `f2f009d020f8407c091c378a571faad5e2912ca181b06edf4055718241f74e3d`
- Pre-canary Restaurant dump SHA-256: `0495f7abfa4130eef6cad97e1957a7a97f2ea040adb0d834c68fd5e4885e0c15`
- Startup guards: ปฏิเสธ Platform mode เมื่อ projector ปิด และเมื่อ actual PostgreSQL database names
  ไม่แยกครบสามฐาน
- Legacy baseline: login, `/auth/me` และ refresh-token placement ผ่าน; token hash อยู่เฉพาะ legacy
- Platform canary: login, refresh rotation, logout, `/auth/me`, `/auth/permissions` และ
  `/auth/switch-branch` ผ่าน Platform identity source
- Cross-slice proof: Platform-issued access token เรียก legacy Restaurant `/restaurant/brands` ผ่าน
- Platform token isolation: login/switch/rotated refresh-token hashes ไม่ปรากฏใน legacy
- User projection: final canary event `9722568d-a8c7-41c6-b74d-743501478648` processed และมี
  Restaurant ledger row; `last_login_at` parity ผ่าน
- Rollback proof: final mode กลับ `legacy/false`, Platform-issued access token ยังผ่าน `/auth/me`,
  Platform refresh token ได้ `401`, legacy re-login ผ่าน
- Rehearsal script มี EXIT/signal trap เพื่อ recreate backend กลับ `legacy/false` หาก canary หยุดกลางทาง
- Final heads: legacy `6b7c8d9e0f12`, Platform `p1platform0003`, Restaurant `p1restaurant0003`
- Final projection parity: Company 1, Branch 4, Brand 3, BrandBranch 7, User 7 ตรงกัน
- Final outbox/ledger: 25 events processed, 0 pending, Restaurant ledger 25
- Final backup: `/private/tmp/restaurant-cutover06-complete/restaurant-boundaries-local-20260731T181417Z`
- Final Platform dump SHA-256: `2b33a6242ad8605ce45269ee95405296bc46ffe88ee6e10910a4fddbd1be6e44`
- Final Restaurant dump SHA-256: `5dacca26cf663b24fece6564c7e5ccccae0b09732474cf35d69d96e164e6b155`
- Final restore drill: restore เข้า temporary Platform/Restaurant databases, ตรวจ boundary metadata ผ่าน
  และลบ drill databases สำเร็จ
- Final readiness: legacy, Platform, Restaurant, Redis และ uploads เป็น `ok`; runtime แสดง
  `identity_database=legacy`, `reference_projector_enabled=false`
- Backend regression: 114 tests ผ่าน
- Restaurant functional smoke: ผ่าน
- Restaurant permission smoke: ผ่าน
- Commit: บันทึกใน Git history ของ Scope ID นี้
