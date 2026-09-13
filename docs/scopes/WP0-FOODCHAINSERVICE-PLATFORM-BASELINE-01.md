# WP0-FOODCHAINSERVICE-PLATFORM-BASELINE-01 — Pre-restructure Baseline

วันที่ตรวจรับอัตโนมัติ: 2026-09-13

สถานะ: **completed — baseline พร้อมเริ่มปรับโครงสร้าง แต่ยังไม่ deploy หรือ rename repository**

## การตัดสินใจด้านชื่อและโครงสร้าง

- ชื่อผลิตภัณฑ์: `Foodchainservice`
- ชื่อโครงการ: `Foodchainservice Platform`
- ชื่อ repository เป้าหมายในอนาคต: `foodchainservice-platform`
- repository ที่ใช้งานจริงใน WP0 ยังคงเป็น `chaiyanutaiagent/restaurant`
- baseline tag: `pre-foodchainservice-platform-20260913`
- development branch ถัดไป: `codex/foodchainservice-platform`

โครงสร้างเป้าหมาย:

```text
Foodchainservice
└── Customer Register / Company Admin
    ├── ERP และรายงานรวม
    ├── Central Kitchen / Supply Chain
    ├── Retail POS
    ├── Restaurant POS
    ├── Takeaway POS
    └── Hotel PMS
```

Control Plane กลางเป็นเจ้าของ Company, Brand, Branch, Identity, สิทธิ์ และ entitlement
ส่วนข้อมูลปฏิบัติการของ Restaurant, Takeaway, Retail และ Hotel ต้องแยก boundary กัน
ครัวกลางและ supply chain เป็น shared service ที่รับคำสั่งผลิตจากหลายแบรนด์และตัดวัตถุดิบ
กองกลางได้โดยไม่ทำให้ operational tables ของ POS แต่ละประเภทปะปนกัน

## ขอบเขต WP0

- freeze code และ database baseline ก่อนปรับโครงสร้าง
- ยืนยันว่า branch ปัจจุบันมี `origin/main` ครบ โดยไม่ merge ย้อนหรือ rewrite history
- ตรวจ backend, frontend, Takeaway end-to-end และ migration heads
- สร้าง rollback backup ทั้งระบบเดิมและ database boundaries
- ทดลอง restore ชุด boundary ลงฐานชั่วคราวแบบไม่เขียนทับข้อมูลใช้งาน
- ตรวจ tracked source หา credential/token รูปแบบที่รู้จัก
- บันทึกหลักฐาน, ติด tag และเปิด branch สำหรับงานแพลตฟอร์มถัดไป

Out of scope:

- ไม่ deploy UAT หรือ Production
- ไม่เปลี่ยน Cloudflare Tunnel, domain หรือ runtime flags
- ไม่ rename GitHub repository, Docker services, database names หรือ public routes
- ไม่ย้าย Chambo/Retail production data และไม่เปิด Hotel module
- ไม่แตะไฟล์ local ที่ยังไม่ track ได้แก่ `pos-dashboard-2023-11-27-05-21-16-utc.zip`
  และ directory `pos/`

## Baseline source

- source integration branch: `codex/p6-takeaway-boundary`
- integration code commit: `8be6dae` (`test: make takeaway smoke date independent`)
- `origin/main` เป็น ancestor ของ baseline และ baseline นำหน้า `origin/main` 43 commits
- การแก้ smoke test ใช้วันทำการปัจจุบันตาม timezone `Asia/Bangkok` เพื่อไม่ให้ QR/Pickup
  token หมดอายุจากวันที่ hard-code

## หลักฐานการตรวจ

| Gate | ผล |
| --- | --- |
| Backend regression | `251` tests ผ่าน |
| Frontend | Type-check และ production build ผ่าน |
| Takeaway service smoke | ผ่าน; QR/Pickup จบที่ `picked_up`, replay/idempotency ผ่าน |
| Shared central stock | สองแบรนด์ตัดวัตถุดิบกองเดียว คงเหลือ `5.0000` ตาม expected |
| Refund stock | คืนกลับ stock location เดิมเป็น `9.0000` ตาม expected |
| Chambo synthetic import | 10 records; opening stock `50.0000`; credit `1500.00`; historical side effect `0` |
| Secret pattern scan | tracked source ไม่พบ finding ตามรูปแบบ private key/access token ที่ตรวจ |
| Git baseline | `origin/main...baseline = 0 behind / 43 ahead` ก่อนเพิ่มเอกสาร WP0 |

Migration heads ที่ตรวจจากฐาน local:

| Database | Migration head |
| --- | --- |
| `restaurant_pos_db` | `6b7c8d9e0f12` |
| `restaurant_platform_core_db` | `p12platform0016` |
| `restaurant_ops_db` | `p6restaurant0007` |
| `takeaway_ops_db` | `p6takeaway0004` |

คำเตือนที่พบจาก regression เป็น development/test JWT key ยาว 30 bytes ซึ่งเป็นค่าทดสอบเดิม
ไม่ใช่ production credential; ก่อน production activation ต้องตรวจ secret จริงให้ยาวอย่างน้อย 32 bytes

## Rollback evidence

Full local backup:

`/private/tmp/foodchainservice-wp0-full-backups/restaurant-pos-local-20260913T071134Z`

- legacy PostgreSQL dump SHA-256:
  `390bfdd29270f22f4765b44fca8d15c9c63df010c157139a0aed1305e3a25a4f`
- Redis archive SHA-256:
  `209b7264d11b09ab3267df3b78a332a8bd1d05c9cff774d71a3e9cffecd73a1b`
- uploads archive SHA-256:
  `58908a76503cb4ad5398e34236eede764a13fd78de8e0f7d4d306314825cf653`
- PostgreSQL custom archive เปิดอ่าน TOC ได้ `1027` entries
- Redis และ uploads archives ผ่านการตรวจ archive integrity
- ไฟล์ทั้งหมดตั้ง permission เป็น owner-only (`0600`)

Boundary backup:

`/private/tmp/foodchainservice-wp0-boundary-backups/restaurant-boundaries-local-20260913T071147Z`

- Platform SHA-256:
  `da7ac3ec0a88b628d6fc2f98771cc9f2da7bb5fa834fcc4f791e8c3e43bc652a`
- Restaurant SHA-256:
  `06c6259e459b828eb7a52ddbf0fb6de2e1e41626e589ab167208b53d87897f08`
- Takeaway SHA-256:
  `70cde6b5064fb0dec7911d228077fa733d8c08ec497d8ba404cfcbda77fd6b40`
- isolated restore drill ผ่าน โดย metadata ตรงกับ `platform_core`, `restaurant`, `takeaway`
- drill databases ถูกลบหลังตรวจสำเร็จ และไม่มีการ restore ทับฐานใช้งาน

Backup ใน `/private/tmp` เป็น local rollback artifact อาจถูกระบบปฏิบัติการล้างได้ จึงไม่ใช้แทน
production/off-device backup ก่อน migration หรือ deployment จริง

## WP0 Gate

- [x] freeze baseline และยืนยันความสัมพันธ์กับ `origin/main`
- [x] backend/frontend regression ผ่าน
- [x] Takeaway และ Chambo synthetic smoke ผ่าน
- [x] migration heads ถูกบันทึก
- [x] full backup และ boundary backup พร้อม checksum
- [x] isolated boundary restore drill ผ่าน
- [x] tracked secret pattern scan ผ่าน
- [x] ไม่มี UAT/Production deployment หรือ external rename ใน WP0
- [x] เตรียม baseline tag และ development branch สำหรับงานถัดไป

หลัง commit เอกสารนี้ ให้ติด tag ที่ commit เดียวกันแล้วสร้าง branch ถัดไปจาก tag โดยตรง
การเริ่ม WP1 ต้องมี Scope ID, acceptance criteria และ rollback ของ WP1 แยกต่างหาก
