# Foodchainservice Platform Module Map

สถานะ: WP2 server-owned Company access contract

Foodchainservice แยกทางเข้าและโมดูลตามความรับผิดชอบดังนี้:

```text
Foodchainservice
├── Customer Register                /signup
├── Company Admin                    /admin
├── Platform Owner Control Plane     /platform/*
└── Company workspaces               /
    ├── ERP และรายงาน                /admin
    ├── Central Kitchen/Supply Chain /restaurant/brands (temporary entry)
    ├── Restaurant POS               /restaurant/*
    ├── Takeaway POS                 /takeaway/*
    ├── Retail POS                   /pos/*
    └── Hotel PMS                    planned; no route
```

Frontend source of truth อยู่ที่:

- `frontend/src/config/platformBrand.ts` สำหรับชื่อผลิตภัณฑ์
- `frontend/src/config/platformModules.ts` สำหรับ stable module key, route, availability,
  registration state, permission hints และ business type

Server source of truth สำหรับสิทธิ์ระดับ Company อยู่ที่:

- `SaasPlan.feature_flags` — โมดูลที่รวมอยู่ในแพ็กเกจ
- `PlatformTenantProfile.feature_flags` — สวิตช์ที่ Platform Owner เปิดให้ Company
- `backend/app/services/company_module_access_service.py` — canonical mapping, lifecycle,
  permission และ runtime readiness
- `GET /api/v1/membership/modules` — สถานะ effective ของ Company/user ปัจจุบัน
- `GET/PUT /api/v1/platform/companies/{company_id}/modules[...]` — การอ่าน/แก้ไขของ Platform Owner

## Stable module keys

| Key | Group | Runtime state | Registration | Operational boundary |
| --- | --- | --- | --- | --- |
| `company_admin` | control | active | not applicable | Platform/legacy during cutover |
| `erp` | shared service | active | not applicable | Legacy ERP during cutover |
| `central_kitchen` | shared service | active ผ่านหน้าเดิม | not applicable | Restaurant boundary ปัจจุบัน |
| `restaurant_pos` | POS | active | open | Restaurant database เมื่อ cutover |
| `takeaway_pos` | POS | dark launch | closed | Takeaway database |
| `retail_pos` | POS | active compatibility | closed | Legacy/Retail target boundary |
| `hotel_pms` | POS/service | planned | closed | ยังไม่มี operational boundary |

## Access rules

- frontend registry ยังมีหน้าที่จัด presentation และ entry route แต่สถานะ Company มาจาก server
- effective access ต้องผ่าน lifecycle, plan, Company flag, permission และ runtime ทุกชั้น
- frontend ซ่อนโมดูลที่ผู้ใช้ไม่มี permission และปิด entry เมื่อ module API ใช้งานไม่ได้
- backend route guards, signed identity context, Company/Brand/Branch scope และ database selection
  ยังคงเป็นผู้ตัดสินสิทธิ์จริง
- `dark_launch` ต้องมี plan, Company flag, permission และ runtime flag พร้อม จึงเปิดได้
- `planned` ไม่มี entry route และต้อง render เป็น disabled/non-link
- registration state แยกจาก runtime state; โมดูลที่รันภายในได้อาจยังไม่เปิดรับลูกค้าใหม่
- Platform update รับเฉพาะ stable key, ต้องมี reason, ตรวจ Platform session และสร้าง Audit Log

## Compatibility rules

- WP1 ไม่เปลี่ยน public หรือ authenticated route เดิม
- Restaurant QR URLs, Takeaway ordering/pickup URLs และ device routes ต้องคงเดิม
- Company Admin และ Platform Owner ใช้ authentication store/guard คนละชุดเหมือนเดิม
- Central Kitchen ยังใช้ Restaurant pages เป็น temporary entry จน work package แยก service ได้รับอนุมัติ
- key เดิม `restaurant`, `takeaway`, `retail_pos` ถูก map เข้าชื่อ canonical โดยไม่บังคับ data migration
- plan code เดิมที่ยังไม่มี `SaasPlan` ใช้ profile เดิมชั่วคราวเพื่อไม่ตัดสิทธิ์ tenant โดยไม่ตั้งใจ
- การเปลี่ยนแพ็กเกจจะไม่เขียนทับ Company module switches ที่ Platform Owner ตั้งไว้
