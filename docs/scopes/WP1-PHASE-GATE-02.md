# WP1-PHASE-GATE-02 — Foodchainservice Shell Verification

วันที่ตรวจรับอัตโนมัติ: 2026-09-13

สถานะ: **passed_local — พร้อมส่งต่อ WP2; ยังไม่ deploy UAT/Production**

Baseline rollback: `pre-foodchainservice-platform-20260913`

## สิ่งที่ส่งมอบ

- product identity contract กลางสำหรับ `Foodchainservice`, Company Admin และ Platform Owner
- typed module map กลางที่มี stable key, group, route, runtime state, registration state,
  permission hints และ business type
- Customer Register แสดง Restaurant POS, Retail POS, Takeaway POS และ Hotel PMS จาก registry
  เดียวกัน โดยเปิดสมัครเฉพาะ Restaurant POS
- workspace selector แสดง ERP, Central Kitchen, Restaurant, Retail และ planned Hotel ตามสถานะ
- Takeaway dark launch ไม่แสดงต่อสาธารณะและแสดงเฉพาะ user ที่มี `takeaway.*` permission
- Company Admin และ Platform Owner ใช้ชื่อ Foodchainservice ที่แยกบทบาทชัดเจน
- PWA manifest, browser title, API display name และเอกสาร architecture ใช้ชื่อผลิตภัณฑ์ใหม่
- route เดิมทั้งหมดคงอยู่ และ module map ไม่ทำหน้าที่แทน backend authorization

## Commits ตาม delivery slice

| Slice | Commit | ผลลัพธ์ |
| --- | --- | --- |
| WP1-A | `b7262da` | product identity, module registry และ architecture contract |
| WP1-B | `4830fd1` | workspace selector และ Customer Register ใช้ registry กลาง |
| WP1-C | `498fe72` | Company Admin, Platform Owner และ shared shell branding |

## Automated evidence

| Gate | ผล |
| --- | --- |
| Frontend type-check | ผ่าน |
| Frontend production/PWA build | ผ่าน; 4,202 modules transformed |
| Browser regression | `16` Playwright tests ผ่าน |
| Public module visibility | active modules แสดง, Hotel disabled, Takeaway dark launch ถูกซ่อน |
| Authorized Takeaway visibility | ผู้มี `takeaway.catalog.view` เห็น entry; module อื่นที่ไม่มีสิทธิ์ถูกซ่อน |
| Route compatibility | `/restaurant`, `/pos`, `/takeaway` คง route และ auth guard เดิม |
| Customer Register | Restaurant เปิดสมัคร; Retail/Takeaway/Hotel disabled ตาม registry |
| Platform/Company separation | Platform Owner และ Company Admin login/session guards ผ่าน |
| Backend regression | `251` tests ผ่าน |
| Takeaway service/import smoke | ผ่าน; QR/Pickup, stock, refund, ERP replay และ synthetic import ผ่าน |
| Tracked secret pattern scan | ไม่พบ finding |

Migration heads ไม่เปลี่ยนจาก WP0:

| Database | Migration head |
| --- | --- |
| `restaurant_pos_db` | `6b7c8d9e0f12` |
| `restaurant_platform_core_db` | `p12platform0016` |
| `restaurant_ops_db` | `p6restaurant0007` |
| `takeaway_ops_db` | `p6takeaway0004` |

คำเตือนที่ไม่บล็อก gate:

- production build ยังมี large chunk warning เดิม ควรทำ code splitting ในงาน performance แยก
- backend test ใช้ development JWT key ยาว 30 bytes; production activation ต้องใช้ secret
  อย่างน้อย 32 bytes ตาม gate เดิม

## Security และ compatibility

- frontend permission filtering เป็น UX เท่านั้น; backend route guards และ signed context ยังบังคับสิทธิ์จริง
- planned module ไม่มี link/route และ dark launch ไม่เปิดให้ anonymous
- ไม่เพิ่ม table, migration, cross-database query หรือ distributed transaction
- ไม่เปลี่ยน Restaurant QR, Takeaway order/pickup, device, Company Admin หรือ Platform routes
- ไม่แก้ Cloudflare, runtime feature flags, UAT หรือ Production deployment

## Rollback

- revert WP1 commits ย้อน `WP1-C → WP1-B → WP1-A`
- หรือสร้าง branch ใหม่จาก `pre-foodchainservice-platform-20260913`
- ไม่มี data migration; ไม่ต้อง restore database สำหรับ rollback ปกติ
- สำรองข้อมูล WP0 อยู่ที่ `/Users/user/Backups/Foodchainservice/WP0-20260913`

## งานภาคสนามที่ยังไม่ใช่เงื่อนไขของ local gate

- Safari บน Mac และ physical iPad visual/touch walkthrough
- UAT/Production deployment และ cache/service-worker verification ผ่าน domain จริง

งานเหล่านี้ต้องทำก่อน production activation แต่สามารถพักไว้ระหว่างพัฒนา WP2 ตามคำสั่งเจ้าของระบบ
