# WP31 — Retail POS Dedicated-Database Pilot Readiness

วันที่: `2026-09-18`
สถานะ: **engineering_ready — real scope, hardware and owner cutover pending**

## Automated evidence

| Gate | ผล |
| --- | --- |
| Retail focused contracts | `35/35` ผ่าน |
| Retail schema | downgrade `v2 → v1` และ re-upgrade `v1 → v2` ผ่าน |
| Selective migration | Company/Brand/Branch scope, count/digest และ replay exact ผ่าน |
| POS canary | barcode, shift, sale, refund, void, stock และ net report ผ่าน |
| Shared ERP | Retail outbox/report projection ผ่าน |
| Write isolation | Legacy source ไม่เปลี่ยนระหว่าง dedicated Retail canary |
| Rollback | route กลับ Legacy และ barcode read ผ่าน |
| Artifact | `/private/tmp/restaurant-wp31-retail/wp8-retail-cutover-20260918T060236Z/manifest.txt` |

Production ปัจจุบันยังตั้ง `RETAIL_SERVICE_DATABASE=legacy`; ฐาน `retail_ops_db` อยู่ head
`p8retail0002` แต่ยังไม่รับ traffic จริง

## Cutover hard gates

- [ ] owner ระบุ Retail Company/Brand/Branch/Product/Location จริงที่จะย้าย
- [ ] สร้าง backup ก่อน cutover และตรวจ count/digest/amount/stock กับผู้รับผิดชอบ
- [ ] scanner, receipt printer, cash drawer และ offline/reconnect ผ่านที่สาขา
- [ ] freeze window, monitoring owner และ rollback owner ถูกระบุ
- [ ] owner ลงชื่อก่อนเปลี่ยน Production routing เป็น `retail`

## Decision

Retail dedicated database และ rollback tooling พร้อม แต่ต้องคง Production routing ที่ Legacy จน external gates ครบ
