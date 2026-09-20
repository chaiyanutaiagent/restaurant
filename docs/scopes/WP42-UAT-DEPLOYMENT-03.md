# WP42 UAT Deployment and Smoke Report

วันที่: `2026-09-20`
ผล: **PASS — Customer Company Shell UAT engineering + visual gate**
Production: **Unchanged / not approved**

## 1. Release identity

- Repository: `chaiyanutaiagent/restaurant`
- Branch: `codex/foodchainservice-platform`
- Implementation commits:
  - `f78a7bb` — `feat: integrate customer company shell WP42`
  - `2988072` — `fix: enforce WP42 keyboard and touch accessibility`
- Final UAT release: `wp42-2988072`
- UAT URL: `https://uat-pos.foodchainservice.com`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/2988072`
- Frontend image: `restaurant-pos-frontend:wp42-2988072`
- Unchanged backend image: `restaurant-pos-backend:wp36-41-0ca50c5`
- Unchanged nginx image: `restaurant-pos-nginx:wp36-41-0ca50c5`

การ deploy เปลี่ยนเฉพาะ frontend ของ compose project `restaurant-pos-uat-drill` และ recreate UAT nginx
เพื่อรับ upstream ใหม่ ไม่มี database migration และไม่ได้สร้าง PostgreSQL, Redis หรือ Cloudflare Tunnel ใหม่

## 2. Scope verified

- Customer Company shell และ permission-aware navigation
- Company/Brand/Branch context switch โดยใช้ signed branch token และล้าง cache เดิม
- Company Dashboard และ partial/freshness states
- App Launcher พร้อม Product Readiness, data source และ allowed actions
- Action Center พร้อม filters, safe deep links และ action ที่ backend รองรับจริง
- Device/Sync status ที่ normalize สถานะ operational
- Loading, Empty, Error, Offline, Stale และ Permission denied
- UAT indicator, keyboard focus/skip link และ tablet touch target อย่างน้อย `44x44`

Hotel PMS ที่ยัง `planned` ไม่แสดงเป็นทางเข้าใช้งาน, Takeaway `dark_launch` ไม่มีลิงก์ทำธุรกรรม
และ Central Kitchen `read_only` แสดงเป็นการดูข้อมูลเท่านั้น

## 3. Automated and local evidence

- Frontend TypeScript type-check: ผ่าน
- Frontend production/PWA build: ผ่าน (`4,233` modules)
- Company shell E2E: `6/6` ผ่านใน `43.3s`
- Foundation backend focused regression: `13/13` ผ่าน
- Runtime dependency audit: `0` high vulnerabilities จาก `npm audit --omit=dev --audit-level=high`
- Git diff/whitespace gate: ผ่านก่อน implementation commits

E2E ครอบคลุม dashboard/context/readiness/stale/sync, tablet launcher, read-only/dark-launch rules,
Action Center mutation payload พร้อม audit reason/owner, ทุก required UI state, signed context switch,
keyboard skip link และ touch targets

คำเตือนที่ไม่บล็อก gate: frontend build ยังมี bundle chunk ใหญ่กว่า `500 kB`; ให้ติดตามในงาน
performance/code-splitting ภายหลัง โดยไม่กระทบความถูกต้องของ WP42 gate นี้

## 4. Live UAT evidence

- `/`, `/company`, `/company/apps`, `/company/actions`, `/admin`: HTTP `200`
- `/health/ready`: ผ่าน
- Company Foundation live smoke: `31` assertions ผ่าน
- Role-based landing: `5` กรณีผ่าน
- Permission allow/deny boundary: ผ่าน
- Role smoke mutation count: `0`
- Recent nginx HTTP `5xx` หลัง final deploy: `0`

Action Center ของข้อมูล UAT จริงยังเป็น empty dataset; การแสดงรายการและ mutation contract
ถูกตรวจด้วย integration mocks และ backend contract โดยไม่สร้างธุรกรรมธุรกิจใน UAT

## 5. Desktop and tablet visual UAT

- Chromium desktop `1440x900`: Company Dashboard แสดง layout/context/status ถูกต้องและไม่มี horizontal overflow
- Chromium tablet `820x1180`: App Launcher แสดง responsive layout, ไม่มี Hotel entry,
  ไม่มี dark-launch link และไม่มี horizontal overflow
- Safari desktop: Company shell และ App Launcher แสดงผลถูกต้องบน UAT URL จริง
- Safari tablet landscape `1024x768`: responsive drawer header และ two-column cards แสดงผลถูกต้อง
- Action Center แสดง empty state ที่ tablet width ถูกต้อง

## 6. Runtime boundaries

| Setting | Effective UAT value | Result |
| --- | --- | --- |
| Identity database | `platform_core` | ไม่เปลี่ยน |
| Restaurant service database | `legacy` | ไม่เปลี่ยน |
| Retail service database | `retail` | ไม่เปลี่ยน |
| Takeaway service database | `takeaway` | ไม่เปลี่ยน |
| Central Kitchen writes | `false` | ไม่เปิดธุรกรรม |
| Company Distribution writes | `false` | ไม่เปิดธุรกรรม |

ไม่มีการเปลี่ยน Retail data source, เปิด Takeaway/Central Kitchen write, สร้างเอกสารภาษีจริง
หรือเปิด Production flag

## 7. Rollback readiness

Pre-WP42 UAT backup:

`/home/behappyaiagent/restaurant-uat-deploy-backups/wp42-before/restaurant-pos-uat-20260920T075213Z`

ตรวจแล้ว:

- backup ของ `legacy`, `platform`, `restaurant`, `retail`, `takeaway`, Redis และ uploads พร้อม checksum
- database dumps อ่าน catalog ได้ด้วย `pg_restore -l`
- previous release `/home/behappyaiagent/restaurant-uat-releases/f78a7bb` พร้อมใช้
- Foundation baseline `/home/behappyaiagent/restaurant-uat-releases/0ca50c5` พร้อมใช้
- previous frontend และ Foundation backend/frontend/nginx images ยังอยู่ครบ
- previous compose configuration validate ผ่าน

WP42 ไม่มี schema/data migration ดังนั้น application rollback ใช้การสลับ frontend image/release กลับก่อน;
restore data เฉพาะเมื่อมีหลักฐานว่า data ถูกกระทบ การ rollback จริงไม่ได้รันเพราะ final UAT ผ่าน

## 8. Production verification

Production backend/frontend/nginx container IDs และ image tags ตรงกับค่าก่อน deploy UAT ทุกตัว
ไม่มี Production service ถูก restart หรือ activate จากงานนี้

## 9. Decision

ปิด WP42 ในระดับ local/UAT engineering + visual gate ได้ และอนุญาตให้จัดทำขอบเขต WP43
แต่ยังไม่อนุญาตให้เริ่ม Production deployment หรือขยาย transaction/data-source/tax scope ที่ระบุเป็นข้อห้าม
