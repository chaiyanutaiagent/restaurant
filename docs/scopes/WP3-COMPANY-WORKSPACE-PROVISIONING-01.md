# WP3-COMPANY-WORKSPACE-PROVISIONING-01 — Company Workspace Provisioning

วันที่วางแผน: 2026-09-13

สถานะ: **completed_local — implementation และ automated gate ผ่าน; ยังไม่ deploy**

Baseline: WP2 gate บน branch `codex/foodchainservice-platform`

## เป้าหมาย

ทำให้ Company Admin จัดโครงสร้างการใช้งานตามภาพ Foodchainservice ได้จากหน้ากลาง:

```text
Customer Register
└── Company Admin
    ├── ERP / Shared services
    ├── Central Kitchen / Supply Chain
    │   ├── Restaurant POS workspaces
    │   └── Takeaway POS workspaces (dark launch)
    ├── Retail POS workspaces (compatibility)
    └── Hotel PMS (planned; create ไม่ได้)
```

WP3 ใช้ Company/Brand/Branch และ business context ที่มีอยู่ ไม่สร้าง operational record ข้ามฐาน
และไม่เปิด Takeaway/Retail/Hotel ให้ลูกค้าจริง

## งานในขอบเขต

### WP3-A — Workspace directory contract

- audit `BrandNavigationService`, Brand/Branch provisioning และ business type validation เดิม
- กำหนด server response สำหรับ workspace directory โดยอ้าง module access จาก WP2
- ห้าม client ส่ง target database เอง; server derive จาก signed business context
- Central Kitchen เป็น Company shared workspace และยังใช้ Restaurant boundary ชั่วคราว

### WP3-B — Idempotent provisioning

- Company Admin สร้าง Restaurant Brand/Branch จาก module ที่ effective ได้
- provisioning ซ้ำต้องไม่สร้าง Brand/Branch ซ้ำ
- ตรวจ plan limits, permission, Company scope และ module access ก่อน write
- Takeaway create เปิดเฉพาะ internal dark-launch runtime; Retail คง compatibility; Hotel ปฏิเสธ
- ทุก provisioning action มี audit และ rollback/disable โดยไม่ลบ operational history

### WP3-C — Company Admin information architecture

- จัด Company Admin ให้เห็น shared services และ workspaces ตาม hierarchy เดียวกัน
- selector แสดง Brand/Branch ที่เข้าถึงได้และเหตุผลเมื่อ module ยังไม่พร้อม
- คง URL `/admin`, `/restaurant`, `/takeaway`, `/pos` และ QR เดิม
- ไม่ซ้ำ controls ของ Platform Owner ในหน้า Company Admin

### WP3-D — Gates

- tenant isolation, scope, permission, plan/module denial และ idempotency tests
- Restaurant provisioning และ route regression
- Takeaway dark-launch negative/positive gates โดยใช้ข้อมูลสังเคราะห์เท่านั้น
- frontend type-check/build/browser tests และ backend full regression
- ไม่มี UAT/Production deployment ระหว่าง WP3

## นอกขอบเขต

- ไม่ย้าย Central Kitchen ออกจาก Restaurant database
- ไม่ import ข้อมูล Chambo จริง
- ไม่สร้าง Hotel operational schema
- ไม่แยก Retail database หรือ redesign Retail POS ใน WP3
- ไม่เปิด billing collection, Cloudflare route หรือ production activation
- ไม่เปลี่ยนชื่อ Git repository, Docker project หรือ database

## Acceptance criteria

- [x] workspace directory มาจาก server และผูกกับ Company/module/business context
- [x] Company Admin สร้าง workspace ได้เฉพาะ module ที่ effective และตัวเองมีสิทธิ์
- [x] provisioning ซ้ำเป็น idempotent และไม่สร้างข้อมูลซ้ำ
- [x] client เลือก target database เองไม่ได้
- [x] Central Kitchen/Restaurant hierarchy แสดงตรงกับโครงสร้าง Foodchainservice
- [x] Takeaway ยัง dark launch, Hotel ยัง planned และ Retail ยัง compatibility
- [x] tenant isolation, audit และ backend route guards ผ่าน
- [x] ไม่มี migration โดยไม่จำเป็น; ใช้ isolated database rehearsal ยืนยันแทน
- [x] backend/frontend/browser regression ผ่าน
- [x] ไม่มี UAT/Production activation ระหว่าง WP3

## Rollback

- ปิด Company Admin provisioning UI ก่อน
- revert workspace directory/provisioning API โดยคง Brand/Branch เดิมไว้
- ห้ามลบ workspace ที่สร้างแล้วอัตโนมัติ; ใช้ deactivate พร้อม audit
- ใช้ WP2 commit เป็น code rollback point

## Implementation decision

- ใช้ Company/Brand/Branch/BrandBranch เดิมเป็น identity ของ Workspace จึงไม่สร้างตารางซ้ำ
- `GET /api/v1/membership/workspaces` เป็น directory กลางของ Company Admin และอ่าน Company
  จาก signed session เท่านั้น
- `POST /api/v1/membership/workspaces` รับ stable module key กับ business identity แต่ไม่รับชื่อฐานข้อมูล
  โดย server เป็นผู้ derive business type และ operational entry route
- provisioning ล็อก Company, ตรวจ permission/module/plan limit, รองรับ idempotency key และ natural
  Brand/Branch identity และบันทึก `company.workspace.provision` ใน Audit Log
- การพัก/คืนค่าเปลี่ยนเฉพาะ BrandBranch link พร้อมเหตุผลและ Audit Log จึงไม่ลบ Brand, Branch
  หรือประวัติ operational เดิม
- ถ้า identity อยู่ `platform_core` จะส่ง reference outbox เฉพาะ aggregate ที่สร้าง/เปลี่ยนจริง
- Company Admin UI อยู่ที่ `/workspaces`; ERP และ Central Kitchen เป็น shared service ส่วน POS
  แสดงแยกตาม Brand/Branch และสถานะจาก WP2

หลักฐานตรวจรับอยู่ที่ `docs/scopes/WP3-PHASE-GATE-02.md`

งานถัดไปที่กำหนดไว้คือ `docs/scopes/WP4-SHARED-ERP-REPORTING-CONTRACT-01.md`
