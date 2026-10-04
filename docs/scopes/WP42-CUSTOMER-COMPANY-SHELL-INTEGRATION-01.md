# WP42 — Customer Company Shell Integration

วันที่จัดทำ: `2026-09-19`
วันที่ปิดงาน: `2026-09-20`
สถานะ: **Closed — local + UAT engineering and visual gate passed; Production not approved**
Dependency: **WP36–WP41 Foundation UAT gate passed**
Target: **Desktop and tablet web; UAT first**

## 1. Outcome

เชื่อม UX/UI ของพื้นที่บริษัทลูกค้ากับ Foundation จริง โดยมี Company Dashboard, App Launcher,
Action Center, Company/Brand/Branch context switcher, Product Readiness และ Device/Sync status
ที่ใช้ข้อมูลและสิทธิ์จาก backend ชุดเดียวกัน

WP42 เป็นงาน shell และ read experience ไม่เปิดธุรกรรมของ Takeaway/Central Kitchen,
ไม่เปลี่ยน Retail data source, ไม่ทำเอกสารภาษีจริง และไม่ deploy Production

## 2. Surfaces in scope

### 2.1 Customer Company shell

- เมนูถาวร: หน้าหลัก, งานและการแจ้งเตือน, องค์กร, พนักงานและสิทธิ์, การตั้งค่า, แอปทั้งหมด
- แยกจาก Platform Console และ Public/Guest routes ชัดเจน
- route guard และ navigation ใช้ effective permission source เดียวกัน
- แสดง environment `UAT` ให้เห็นชัดและห้ามทำให้ผู้ใช้เข้าใจว่าเป็น Production
- รองรับ desktop และ tablet landscape/portrait; mobile app ไม่อยู่ในขอบเขต

### 2.2 Context switcher

- แสดง Company, Brand, Branch และ Station/Device เมื่อมีค่า
- ใช้ `GET /api/v1/company/context` และ `GET /api/v1/system/me/branches`
- การสลับ Branch ต้องเรียก `POST /api/v1/auth/switch-branch` และใช้ token ใหม่
- หลังสลับ context ต้องล้าง query/cache ของ context เดิมก่อน render ข้อมูลใหม่
- ไม่อนุญาตให้ client header หรือค่าจาก local storage ยกระดับ scope

### 2.3 Company Dashboard

- ใช้ `GET /api/v1/company/overview` เป็น aggregate source
- แสดง task summary และ module sections แบบเสียแยก widget ได้
- ทุก section แสดง readiness, data source, status, freshness และ deep link ที่อนุญาต
- ห้าม frontend join หลาย operational endpoint เพื่อสร้าง Company total เอง

### 2.4 App Launcher and Product Readiness

- ใช้ `GET /api/v1/company/access` เป็น source of truth
- แสดงเฉพาะโมดูลที่เหมาะกับผู้ใช้และสถานะจริง
- Label มาตรฐาน: `production`, `pilot`, `dark_launch`, `read_only`, `legacy`, `planned`
- ปุ่ม/ทางเข้าอิง `effective_access` และ `allowed_actions`; deny by default
- Hotel PMS ที่ `planned` ไม่เป็นทางเข้าใช้งาน
- Takeaway `dark_launch` และ Central Kitchen `read_only` ห้ามมี UI ที่สื่อว่าส่งธุรกรรมจริงได้

### 2.5 Action Center

- ใช้ `GET /api/v1/company/action-center`
- เรียงตาม severity, due time และ business impact ตาม contract
- แสดง unread, source app, owner, context, due date และ deep link
- รอบแรกเชื่อมเฉพาะ action ที่ backend รองรับจริง (`assign`, `acknowledge`, `dismiss`)
- action อื่นแสดงเป็น read-only/roadmap จนมี backend workflow และ approval gate

### 2.6 Device and Sync status

- ใช้ `GET /api/v1/company/operational-status`
- รองรับ state: `online`, `offline`, `degraded`, `pending_sync`, `stale`, `error`, `disabled`
- แสดง last seen, last sync, queue size, source system, error code และ retryability เมื่อมีข้อมูล
- ซ่อนทั้ง surface หรือแสดง Permission denied ตามบริบท ห้ามเรียก retry/action ที่ backend ไม่รองรับ

## 3. Required UI states

ทุก surface ที่ดึงข้อมูลต้องมี state ที่ทดสอบได้แยกกัน:

| State | Expected behavior |
| --- | --- |
| Loading | ใช้ skeleton ที่รักษาขนาด layout และไม่แสดงข้อมูล context เก่า |
| Empty | บอกว่าไม่มีข้อมูล พร้อม next step เฉพาะเมื่อผู้ใช้มีสิทธิ์ทำได้จริง |
| Error | error boundary ระดับ widget/page, retry ได้เมื่อปลอดภัย และไม่ทำทั้ง shell ล่ม |
| Offline | แสดงว่าเป็นข้อมูล cache หรือไม่มี connection; ปิด action ที่ต้องออนไลน์ |
| Stale | แสดงเวลาที่อัปเดตล่าสุดและที่มาของข้อมูล โดยไม่เรียกว่า real-time |
| Permission denied | ไม่เปิดเผยข้อมูล; แสดงทางกลับที่ปลอดภัยและไม่วน redirect |

สถานะ `degraded`, `pending_sync` และ `disabled` ของ Device/Sync ต้องมี semantic badge/ข้อความเฉพาะ
และต้องไม่ถูกยุบรวมเป็น Error ทั้งหมด

## 4. Work breakdown

1. **WP42.1 Shell + navigation** — layout, route boundary, permission-aware menu, UAT badge
2. **WP42.2 Context switcher** — Company/Brand/Branch display, signed branch switch, cache reset
3. **WP42.3 Company Dashboard** — overview widgets, task summary, partial failure and freshness
4. **WP42.4 App Launcher** — readiness/data-source badges, allowed-action and route guards
5. **WP42.5 Action Center** — queue, filter/read state, supported actions and deep links
6. **WP42.6 Device/Sync panel** — normalized states, timestamps, queue/error details
7. **WP42.7 Shared states and UAT** — Loading/Empty/Error/Offline/Stale/Permission denied,
   keyboard/focus/contrast/touch QA, desktop/tablet regression and rollback evidence

## 5. UX and responsive rules

- ใช้ design tokens และ component pattern ที่ทีม UX/UI ส่งมอบ โดยไม่ hard-code readiness/permission
- touch target อย่างน้อย `44x44` และรองรับ keyboard navigation กับ visible focus
- desktop ใช้ workspace density ที่เหมาะกับข้อมูล; tablet ต้องไม่เกิด horizontal overflow ที่ flow หลัก
- context, readiness และ operational status ต้องมองเห็นก่อน action สำคัญ
- ข้อความไทยต้องขยายได้และไม่ใช้สีเพียงอย่างเดียวสื่อ status
- route-level error boundary และ code splitting ต้องไม่ทำให้ shell ทั้งหมดล่มเมื่อโมดูลหนึ่งมีปัญหา

## 6. Security and data rules

- Backend permission และ release gate เป็น authority; การซ่อนปุ่มเป็นเพียง UX
- ห้ามเก็บหรือสร้าง Company/Brand/Branch permission ใหม่ใน frontend
- ห้ามแสดง cached data ข้าม Company/Branch หลัง context switch
- Deep link ต้องรักษา signed context และผ่าน route guard ทุกครั้ง
- Action Center mutation ต้องส่ง reason และแสดงเฉพาะ action ที่ contract อนุญาต
- telemetry/log ต้องไม่บันทึก access token, refresh token หรือข้อมูลลับ

## 7. Acceptance criteria

- ผู้ใช้ทั้งห้า landing class ไป `/company`, `/restaurant`, `/pos`, `/admin`, `/403` ถูกต้อง
- Company/Brand/Branch switch เปลี่ยน token, cache และเนื้อหาพร้อมกันโดยไม่มีข้อมูลเก่าค้าง
- Dashboard, Launcher, Action Center และ Device/Sync ใช้ Foundation API ที่กำหนดเท่านั้น
- readiness, data source และ allowed action ตรงกับ response ของ backend
- ทั้งหก UI state สามารถจำลองและตรวจใน component/integration tests ได้
- Permission denied ไม่เปิดเผยข้อมูล และ API `403` ไม่ทำให้ redirect loop
- desktop และ tablet ผ่าน visual/interaction UAT ใน Safari และ Chromium
- frontend type-check, build, unit/integration tests และ accessibility smoke ผ่าน
- UAT deployment มี immutable release, backup/rollback check และ Production remains unchanged

## 8. Explicitly out of scope

- Production deployment หรือ Production feature activation
- เปิด Takeaway/Central Kitchen real transactions
- เปลี่ยน Retail operational data source หรือ migrate Retail data
- สร้าง/ยื่นเอกสารภาษีจริง
- mobile application หรือ mobile-first transaction flow
- เปลี่ยน WP36–WP41 API contract โดยไม่มี defect/scope review
- Organization, People & Access และ Settings redesign เชิงลึกนอกส่วน navigation/link ของ shell

## 9. Phase gate result

WP42 implementation และ UAT gate ผ่านที่ release `wp42-2988072` โดยมีหลักฐานดังนี้:

- frontend type-check, production/PWA build และ Company shell E2E ผ่าน
- Foundation backend regression ผ่าน `13/13`
- UAT Company Foundation smoke ผ่าน `31` assertions
- role-based landing `5` กรณีและ permission boundary ผ่าน โดย mutation count เท่ากับ `0`
- Desktop/Tablet ผ่าน visual UAT ใน Chromium และ Safari โดยไม่เกิด horizontal overflow
- context switch, Product Readiness, Action Center, Dashboard และ Device/Sync state ผ่านตาม scope
- backup, previous release/image และ rollback configuration พร้อมใช้งาน
- Central Kitchen/Distribution write flags ยังคง `false` และ Production ไม่เปลี่ยน

รายละเอียด deployment อยู่ที่ `docs/scopes/WP42-UAT-DEPLOYMENT-03.md` และคำตัดสิน gate อยู่ที่
`docs/scopes/WP42-PHASE-GATE-02.md` การปิด WP42 ไม่อนุญาต Production deployment,
Takeaway/Central Kitchen transaction activation, Retail data-source change หรือเอกสารภาษีจริง
