# Scope ID: P5-UAT-SECURITY-03

สถานะ: **Automated technical gate passed — physical/visual UAT เลื่อนตามคำสั่ง owner จนกว่าอุปกรณ์จริงจะมา และ owner sign-off ยัง pending**

Phase: **Phase 5 — Platform Onboarding และ Go-live**

## Outcome

- เพิ่ม isolated clean-room gate สำหรับ full UAT ตั้งแต่ QR menu/order → Kitchen
  `pending → cooking → done` → served → cash checkout → recipe stock posting → accounting/outbox
  → Restaurant ERP report โดยปฏิเสธการเขียนหาก Compose project ไม่ขึ้นต้นด้วย `restaurant-p5-uat`
- แก้ dine-in checkout ให้ใช้ `BrandBranch.store_location_id` เป็นตำแหน่งตัดวัตถุดิบของสูตร
  จึงไม่หลุดไป stock location ตัวแรกของ branch และเพิ่ม demo raw-material role เป็น `store_local`
- ยืนยัน exactly-once handoff: payment `1`, operational outbox `1`, journal entry `1`,
  debit/credit เท่ากัน `169.00` และ recipe stock movements `3`
- ยืนยัน ERP report กระทบยอดยอดขาย/ชำระเงิน `169.00` และคำนวณ recipe COGS `66.20`
- ปิด FastAPI docs/OpenAPI โดย default เมื่อ `ENVIRONMENT=production`; development/test เปิดได้ตามเดิม
- เพิ่ม Content Security Policy ให้ production nginx ทั้ง local HTTP, HTTPS template และ Cloudflare variant
- รีเฟรช backend security dependencies และเปลี่ยน JWT implementation จาก `python-jose` เป็น PyJWT 2.13.0
- อัปเกรด React Router เป็น 7.18.1 เพื่อปิดช่องโหว่ CSR/open-redirect รุ่นเดิม โดยคง React 18/Node 20 compatibility

## Automated UAT coverage

คำสั่งหลัก:

```bash
P5_UAT_ADMIN_PASSWORD='UAT_PASSWORD_AT_LEAST_16_CHARS' \
  scripts/rehearse-phase5-uat-security.sh --yes
```

Gate สร้าง volume ใหม่, migrate ถึง head, seed tenant/Brand/Branch/stock/menu/recipe เฉพาะ UAT,
รัน backend regression, full API UAT, dine-in/takeaway smoke, permission smoke, frontend
type-check/build, dependency audits, production API-doc check, nginx build/config/CSP และ repository
safety scan แล้วลบ isolated stack อัตโนมัติ เว้นแต่ระบุ `--keep-running`

ผลวันที่ 1 สิงหาคม 2026:

- backend unit regression `188` tests ผ่าน
- QR-to-ERP full API UAT ผ่าน รวม retry checkout ที่ต้องถูกปฏิเสธเพื่อป้องกันชำระซ้ำ
- dine-in และ takeaway F&B smoke ผ่าน
- Manager, Cashier, Kitchen และ recipe/cost permission smoke ผ่าน
- frontend type-check และ production build ผ่าน
- production API docs/OpenAPI disabled check, nginx syntax และ CSP check ผ่าน
- pre-Git safety scan และ shell syntax ผ่าน; `.env` local ถูก ignore และไม่ได้ stage

## Dependency review

- Backend `pip-audit`: zero known vulnerabilities หลังอัปเกรด FastAPI/Pydantic/Starlette,
  PyJWT, python-multipart, WeasyPrint และ aiosmtplib
- Frontend production audit: `2 high` package rows จาก advisory เดียว
  `GHSA-qwww-vcr4-c8h2` ซึ่งกระทบ React Router RSC-mode Action processing
- Execution-path review: frontend ใช้เพียง declarative `BrowserRouter`; ไม่มี React Router
  Action, SSR, RSC, `RouterProvider` หรือ server runtime และ production image มีเฉพาะ nginx/static assets
- Frontend full audit: `5` package rows (`3 high`, `2 moderate`) รวม production RSC rows ข้างต้น
  และ Vite/esbuild dev-server findings; dev server ไม่อยู่ใน production image
- React Router RSC และ Vite dev-server findings ถูกจัดเป็น non-reachable/operational exceptions
  สำหรับ architecture ปัจจุบัน แต่ยังต้องมี security-owner risk acceptance ก่อน go-live

## Pending owner actions

- [ ] เมื่ออุปกรณ์จริงมาถึง ให้ทำ physical/visual UAT: public QR menu, Kitchen board,
  table/session state, checkout และ ERP report พร้อมตรวจ browser console/CSP
- [ ] ให้ UAT owner ลงนามผลใน `docs/production/sign-off.md` หรือ controlled launch record
- [ ] ให้ security owner ยอมรับ dependency exceptions ที่บันทึกไว้ หรืออนุมัติ migration ข้าม major
- [ ] กรอก production checklist, backup/restore owner, operator handoff และ final go/no-go

Owner สั่งเลื่อน physical/visual UAT เมื่อ 1 สิงหาคม 2026 เพราะอุปกรณ์จริงยังไม่มา จึงไม่มีการอ้างว่า
UAT ส่วนนี้ผ่าน แม้ API chain, frontend build และ production nginx config จะผ่านแล้ว งานที่ไม่ต้องใช้อุปกรณ์
ดำเนินต่อใน `P5-COMPLETION-NONDEVICE-04`

## Safety contract

- Gate เขียนเฉพาะ isolated Compose project/volumes ที่ชื่อขึ้นต้นด้วย `restaurant-p5-uat`
- ไม่มี schema migration ใหม่ ไม่มีการแตะ live database, production secret, DNS/TLS หรือ production deployment
- ไม่มีการสร้าง Platform Owner บนฐาน live และไม่มี commit/push จาก scope นี้
- ห้ามเริ่ม Phase 6 จนกว่า Phase 5 owner sign-off และ Restaurant Completion Gate จะครบ

## Evidence

- Final artifact: `/private/tmp/restaurant-p5-artifacts/p5-uat-security-03-20260801T134532Z/manifest.txt`
- Full UAT context และ record IDs อยู่ใน `full-uat-api.log` และ `browser-context.json` ภายใน artifact directory
- Dependency audit JSON อยู่ใน `backend-dependency-audit.json`,
  `frontend-production-dependency-audit.json` และ `frontend-full-dependency-audit.json`

## Rollback

Scope นี้ไม่มี schema migration การ rollback ทำได้โดย revert application code, dependency pins และ
production nginx headers แล้ว rebuild image ใน isolated environment ก่อนใช้งาน ห้าม rollback ด้วยการแก้ฐาน live
