# WP36–WP41 UAT Deployment and Smoke Report

วันที่: `2026-09-19`
ผล: **PASS — Foundation UAT engineering gate**
Production: **Unchanged / not approved**

## 1. Release identity

- Repository: `chaiyanutaiagent/restaurant`
- Branch: `codex/foodchainservice-platform`
- Commit: `0ca50c5` (`feat: add company foundation WP36-WP41`)
- UAT URL: `https://uat-pos.foodchainservice.com`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/0ca50c5`
- Images:
  - `restaurant-pos-backend:wp36-41-0ca50c5`
  - `restaurant-pos-frontend:wp36-41-0ca50c5`
  - `restaurant-pos-nginx:wp36-41-0ca50c5`

การ deploy เปลี่ยนเฉพาะ `backend`, `frontend` และ `nginx` ของ compose project
`restaurant-pos-uat-drill`; PostgreSQL, Redis และ Cloudflare Tunnel เดิมไม่ถูกสร้างใหม่

## 2. Runtime boundary verified after deployment

| Setting | Effective UAT value | Result |
| --- | --- | --- |
| Environment | `development` ซึ่ง canonical API แสดงเป็น `uat` | ผ่าน |
| Identity database | `platform_core` | ไม่เปลี่ยน |
| Restaurant service database | `legacy` | ไม่เปลี่ยน |
| Retail service database | `retail` | ไม่เปลี่ยน |
| Takeaway service database | `takeaway` | ไม่เปลี่ยน |
| Takeaway feature | `true` | ค่าเดิมก่อน deploy; Readiness ยังคง `dark_launch` |
| Central Kitchen writes | `false` | ไม่เปิดธุรกรรม |
| Company Distribution writes | `false` | ไม่เปิดธุรกรรม |

ไม่มีการเปิด Production flag, เปิด Takeaway/Central Kitchen transaction เพิ่ม,
เปลี่ยน Retail data source หรือสร้างเอกสารภาษีจริง

## 3. Engineering and UAT results

### Image regression

- Backend full regression ภายใต้ default test boundary: `399 passed`, `1 skipped`
- Frontend type-check และ production/PWA build: ผ่านจาก local gate ก่อนสร้าง release
- การรันครั้งแรกด้วย runtime UAT จริงพบ test boundary `4` จุดที่คาดค่า Legacy/Disabled;
  เมื่อตั้งเฉพาะ test process กลับเป็น default boundary ชุดเดิมผ่านทั้งหมด
- ค่า runtime ของ container ที่ให้บริการไม่ได้ถูกเปลี่ยนจากการ rerun tests

### Public and authenticated smoke

- `/`, `/company`, `/company/apps`, `/company/actions`, `/admin`: HTTP `200`
- `/health` และ `/health/ready`: ผ่าน
- Company API เมื่อไม่มี token: ปฏิเสธตาม policy
- Guarded UAT auto-login: ผ่าน
- Canonical Company context และ signed-context transport policy: ผ่าน
- สลับ token จาก Company ไป Brand/Branch ที่มีอยู่จริง: ผ่าน
- Product Readiness ครบ `erp`, `restaurant_pos`, `retail_pos`, `takeaway_pos`,
  `central_kitchen`, `hotel_pms`
- Takeaway และ Hotel ไม่มี allowed action; Central Kitchen ไม่มี write action
- Action Center, Dashboard/Overview, Company Audit และ Device/Sync normalized states: ผ่าน
- Role preset สำคัญพร้อมใช้งาน

Read-only smoke script ผ่าน `31` assertions และไม่สร้างข้อมูลธุรกิจ

### Role and permission smoke

ใช้ token อายุสั้นที่ลงนามภายใน UAT backend กับ UAT superuser เดิม โดยจำกัด permission claim
ตามแต่ละกรณี จึงไม่มีการสร้าง User, Role, Session หรือเอกสารธุรกิจ

| Test role | Expected landing | Result |
| --- | --- | --- |
| Company Owner | `/company` | ผ่าน |
| Restaurant Service | `/restaurant` | ผ่าน |
| Retail Cashier | `/pos` | ผ่าน |
| Back Office | `/admin` | ผ่าน |
| No Access | `/403` | ผ่าน |

Device/Sync endpoint ปฏิเสธ role ที่ไม่มีสิทธิ์และอนุญาต role ที่มี `system.device.view` ถูกต้อง
รวม `2` permission boundary checks ผ่าน และ mutation count เท่ากับ `0`

## 4. Rollback readiness

Pre-deploy backup:

`/home/behappyaiagent/restaurant-uat-deploy-backups/wp36-41-before/restaurant-pos-uat-20260919T035509Z`

ตรวจแล้ว:

- `legacy`, `platform`, `restaurant`, `retail`, `takeaway` database dumps มี checksum ตรงทั้งหมด
- `redis.tar.gz` และ `uploads.tar.gz` มี checksum ตรง
- database dump ทุกไฟล์อ่าน catalog ได้ด้วย `pg_restore -l`
- previous release compose configuration validate ผ่าน
- previous images ยังอยู่ครบ:
  - `restaurant-pos-backend:wp35-dfb2441`
  - `restaurant-pos-frontend:wp35-dfb2441`
  - `restaurant-pos-nginx:wp35-dfb2441`

แนวทาง rollback คือสลับ UAT compose กลับ previous release/images ก่อน และ restore database/volume
เฉพาะเมื่อพบ data incompatibility งานชุดนี้ไม่มี migration จึงคาดว่า image rollback เพียงอย่างเดียวเพียงพอ
ในกรณี application regression การ rollback จริงไม่ได้ถูกรันเพราะ UAT smoke ผ่าน

## 5. Production verification

Production compose project ยังคงใช้ image เดิมก่อนการ deploy UAT และไม่มี service ใดถูก restart
จากงานชุดนี้ จึงไม่มี Production deployment หรือ Production activation แฝง

## 6. Gate decision

ปิด **WP36–WP41 Foundation Phase Gate** ได้ในระดับ engineering/UAT และอนุญาตให้จัดทำขอบเขต WP42
เพื่อเชื่อม UX/UI กับ Foundation

การปิด gate นี้ไม่เท่ากับ Production go-live และไม่แทน Physical Safari/iPad UAT,
accountant sign-off, owner go/no-go หรือ transaction activation gate ของแต่ละผลิตภัณฑ์
