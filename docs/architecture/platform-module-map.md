# Foodchainservice Platform Module Map

สถานะ: WP1 presentation/runtime contract

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

- module map มีหน้าที่จัด presentation และ entry route เท่านั้น ไม่ใช่ authorization
- frontend ซ่อนโมดูลที่ผู้ใช้ไม่มี permission เพื่อให้ UX ตรงกับงานที่ได้รับมอบหมาย
- backend route guards, signed identity context, Company/Brand/Branch scope และ database selection
  ยังคงเป็นผู้ตัดสินสิทธิ์จริง
- `dark_launch` ไม่แสดงต่อผู้ใช้ที่ยังไม่ login และแสดงเฉพาะเมื่อมี permission ของโมดูล
- `planned` ไม่มี entry route และต้อง render เป็น disabled/non-link
- registration state แยกจาก runtime state; โมดูลที่รันภายในได้อาจยังไม่เปิดรับลูกค้าใหม่

## Compatibility rules

- WP1 ไม่เปลี่ยน public หรือ authenticated route เดิม
- Restaurant QR URLs, Takeaway ordering/pickup URLs และ device routes ต้องคงเดิม
- Company Admin และ Platform Owner ใช้ authentication store/guard คนละชุดเหมือนเดิม
- Central Kitchen ยังใช้ Restaurant pages เป็น temporary entry จน work package แยก service ได้รับอนุมัติ
- การย้าย module state ไปเป็น server-owned Company entitlement เป็นขอบเขต WP2 ไม่ใช่ WP1
