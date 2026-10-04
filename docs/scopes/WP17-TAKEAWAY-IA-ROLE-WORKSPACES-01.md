# WP17 — Takeaway Information Architecture และ Role Workspaces

วันที่ตรวจรับ: 2026-09-16

สถานะ: **implemented_local — ผ่าน automated gate; ยังไม่ deploy UAT/Production**

Baseline: `378ba7e00609a4b52e5382d59e44e0afcf7dac1a`

## เป้าหมาย

จัด Takeaway จากเมนูรวมแนวนอนให้เป็นพื้นที่ทำงานตามบทบาท ก่อนนำ workflow Chambo ที่เหลือเข้ามาใน
WP18–WP21 โดยใช้ permission และ scope จาก signed token ไม่ใช้ค่าที่ผู้ใช้พิมพ์ใน URL เพื่อเลือกฐานข้อมูล

## สิ่งที่ส่งมอบ

### 1. Signed workspace context

Frontend เก็บ `brand_id`, `branch_id`, `business_type`, `target_database`, `scope_types` และ permission
จาก access token หลัง login/switch branch พร้อมล้างค่าทั้งหมดเมื่อออกจากระบบ

- Store workspace อนุญาต scope `company`, `branch`, `station`
- Central/Admin workspace อนุญาต scope `company`, `brand`
- session รุ่นเก่าที่ไม่มี `scope_types` ยังทำงานแบบ compatible จนกว่าจะ login ใหม่
- server ยังคงเป็นผู้เลือก Takeaway database และตรวจ business type/feature/permission ซ้ำทุก API

### 2. Navigation แบ่งตามงาน

| พื้นที่ | Route หลัก | ผู้ใช้เป้าหมาย |
| --- | --- | --- |
| ภาพรวม | `/takeaway` | ผู้ใช้ Takeaway ที่มี catalog view |
| หน้าร้าน | `/takeaway/store/*` | Cashier, Branch Manager, Kitchen/Pickup station |
| ส่วนกลาง | `/takeaway/central/*` | Brand Manager, Central Production/Stock operator |
| ผู้ดูแล | `/takeaway/admin/*` | Company/Brand admin, Import/ERP operator |

เมนูถูกกรองทั้ง permission และ signed scope ทำให้พนักงานสาขาไม่เห็น Central/Admin และ Brand Manager
ไม่เห็น Store workspace เมื่อไม่ได้อยู่ใน branch scope

### 3. Canonical routes

Store:

- `/takeaway/store/orders` — Counter
- `/takeaway/store/shifts` — เปิด/ปิดกะและประวัติ
- `/takeaway/store/kitchen` — Kitchen queue
- `/takeaway/store/pickup` — Pickup
- `/takeaway/store/central-orders` — ใบสั่งของสาขา
- `/takeaway/store/stock` — สต๊อกร้าน
- `/takeaway/store/transfers` — รับโอนสินค้า
- `/takeaway/store/reports` — รายงานร้าน
- `/takeaway/store/staff` — ส่งต่อไป User Admin ตามสิทธิ์

Central:

- `/takeaway/central/orders`
- `/takeaway/central/production`
- `/takeaway/central/stock`
- `/takeaway/central/transfers`
- `/takeaway/central/credits`
- `/takeaway/central/recipes`
- `/takeaway/central/reports`
- `/takeaway/central/staff`

Admin:

- `/takeaway/admin/import`
- `/takeaway/admin/cutover`
- `/takeaway/admin/erp`
- `/takeaway/admin/users`

Recipes และ Cutover แสดงสถานะ gate ตามจริงและยังไม่เปิดการ mutation ก่อน WP19/WP21

### 4. Compatibility

ลิงก์เดิม `/takeaway/counter`, `/kitchen`, `/pickup`, `/central-orders`, `/production`, `/stock`,
`/transfers`, `/credits`, `/reports`, `/import`, `/erp` redirect ไป canonical route โดยเลือก Store/Central
จาก permission และ scope ที่ลงนามแล้ว จึงไม่ทำให้ bookmark เดิมเสีย

### 5. Permission correction

แก้ endpoint ดูรายการ Central Order ให้ผู้มี `takeaway.central_order.create` หรือ
`takeaway.central_order.manage` อ่านได้ตามบทบาท ขณะที่การสร้างใบสั่งยังคงต้องใช้ `create` และการเปลี่ยน
สถานะยังคงต้องใช้ `manage` ปุ่มจัดการและ ERP acknowledge ถูกซ่อนเมื่อไม่มีสิทธิ์จริง

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | `365` tests ผ่าน, skipped `1` |
| Focused Takeaway policy | `8` tests ผ่าน |
| Frontend type-check | ผ่าน |
| Frontend production PWA build | ผ่าน, `4,216` modules |
| Takeaway browser role test | `3/3` ผ่าน |

Browser role test ครอบคลุม:

1. Branch cashier เห็นเฉพาะ Store และ legacy counter redirect ถูกต้อง
2. Kitchen-only station เข้า `/takeaway` แล้วไปหน้าครัวแรกที่มีสิทธิ์ ไม่ชน 403
3. Brand Manager เห็น Central/Admin, legacy central route ถูกต้อง และถูกปฏิเสธเมื่อเปิด Store URL ตรง

Build มีคำเตือน chunk ใหญ่เดิม แต่ไม่มี compile/build failure และไม่ใช่ activation blocker ของ WP17

## Boundary และผลกระทบระบบ

- ไม่มี database migration
- ไม่มีการ import Chambo จริง
- ไม่เปลี่ยน feature flag
- ไม่แก้ `/Users/user/Projects/erp-pos-run`
- ไม่ deploy UAT หรือ Production
- Restaurant/Retail routes เดิมไม่ถูกย้าย

## Definition of Done

- [x] Store/Central/Admin แยก route และ navigation ชัดเจน
- [x] Navigation กรองด้วย permission และ signed scope
- [x] Kitchen-only role มี safe landing page
- [x] Bookmark เดิม redirect ได้
- [x] Server permission ของ Central Order แยก create/view-manage ถูกต้อง
- [x] หน้ากะขายแยกจาก Counter
- [x] Type-check/build/backend/browser tests ผ่าน
- [x] ไม่มี migration/deployment/production mutation

งานถัดไป: **WP18 — Store Operation Parity** เริ่มจาก Takeaway offline outbox, receipt/reprint,
shift close summary และ Store Central Order แบบ regular/extra/unlisted/receive
