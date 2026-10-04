# WP36–WP41 Foundation Phase Gate

วันที่: `2026-09-19`
ผล: **PASS — local + UAT engineering gate; Foundation phase closed**
UAT: **Deployed at commit `0ca50c5`; smoke and rollback readiness passed**
Production: **Unchanged / not approved for activation**

## Scope verified

- WP36 canonical signed Company/Brand/Branch/Station context และ role-aware landing
- WP37 product readiness, data-source visibility และ fail-closed allowed actions
- WP38 role presets, last Company Owner protection, Company shell และ read-only App Launcher
- WP39 unified Company Action Center, notification issues, personal unread/dismiss และ audit
- WP40 permission/scope-aware Company/Module overview read API
- WP41 normalized device/sync/integration states และ Company Audit merge across database boundaries

## Automated evidence

- Backend full unit regression: `399` passed, `1` skipped
- WP36–WP41 focused backend contracts: ผ่าน
- Python source/test compile: ผ่าน
- Frontend TypeScript type-check: ผ่าน
- Frontend production/PWA build: ผ่าน (`4,228` modules)
- Git whitespace/error check: ผ่าน

## UAT evidence

- UAT release: `wp36-41-0ca50c5`
- Public health, readiness และ Customer Company shell routes: ผ่าน
- Read-only Company foundation smoke: `31` assertions ผ่าน
- Role-based landing `5` บทบาท และ permission allow/deny boundary `2` จุด: ผ่าน
- Canonical Company → Brand → Branch token switch: ผ่าน
- Product Readiness, Action Center, Company Dashboard และ Device/Sync state: ผ่าน
- Rollback backup checksum, previous images และ previous compose configuration: ผ่าน
- Central Kitchen/Distribution write flags ยังคง `false`
- Production containers และ Production flags ไม่ถูกเปลี่ยน

หลักฐานฉบับเต็มอยู่ที่ `docs/scopes/WP36-WP41-UAT-DEPLOYMENT-03.md`

คำเตือนที่ไม่บล็อก gate: dependency เดิมแจ้ง HMAC test key สั้นและ Starlette TestClient deprecation;
frontend แจ้ง bundle chunk ใหญ่กว่า 500 kB ซึ่งต้องจัดการใน UI performance work package ภายหลัง

## Deliberate non-actions

- ไม่มี database migration
- ไม่เปิด Takeaway real transactions
- ไม่เปิด Central Kitchen/Distribution Production writes
- ไม่เปลี่ยน Retail data source
- ไม่ deploy Production และไม่เปิด Production flags
- ไม่เปิด Takeaway/Central Kitchen transactions เพิ่มจากค่า UAT เดิม
- ไม่เปลี่ยน Retail data source ในการ deploy รอบนี้
- ยังไม่ยกสถานะ Physical UAT, accountant sign-off หรือ owner go/no-go

WP42 มีขอบเขตพร้อมพิจารณาที่ `docs/scopes/WP42-CUSTOMER-COMPANY-SHELL-INTEGRATION-01.md`
แต่ยังไม่ถือว่าอนุมัติ implementation จนกว่าจะได้รับคำสั่งแยก
UI flow ถัดไปต้อง implementation ทีละส่วนโดยอ้างอิง contract ชุดนี้
แต่ action ที่มีผลต่อเงินจริง สต็อก ภาษี และการเปิด Production ยังคงต้องผ่าน release gate เดิม
