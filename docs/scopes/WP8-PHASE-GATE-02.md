# WP8-PHASE-GATE-02 — Retail Selective Migration Verification

วันที่ตรวจรับอัตโนมัติ: 2026-09-15
วันที่ deploy UAT dark launch: 2026-09-16

สถานะ: **uat_dark_launch_passed — UAT ใช้ WP8 release และ Platform identity แล้ว;
Retail database พร้อมแต่ยังไม่รับ traffic; physical UAT/Production ยังพัก**

Baseline rollback: WP7 commit `bc4a93eb773dca924bddee0bac2146ef5156c8ee`

## สิ่งที่ส่งมอบ

- Retail operational schema contract v2 และ strict table manifest
- Platform → Retail reference projection แบบ idempotent โดยไม่ copy password credential
- selective migration ที่ต้องระบุ scope, เรียง FK, replay ได้ และตรวจ count/digest ทุกตาราง
- Retail POS routing ที่ไม่แตะ legacy-only CRM/notification/accounting side effects หลัง cutover
- Retail source stream ไป Company shared ERP reporting
- isolated rehearsal สำหรับ migration downgrade/re-upgrade, backup, canary และ rollback

## Automated evidence

| Gate | ผล |
| --- | --- |
| WP8 focused contracts | `40` tests ผ่าน (`1` skip เมื่อ process ไม่มี Retail URL) |
| Backend full regression | `328` tests ผ่าน (`1` skip ตาม optional Retail URL) |
| Retail schema | `base → v1 → v2 → v1 → v2`; metadata `retail:2` และ manifest ครบ |
| Reference projection | exact count/digest, replay exact, ตรวจและซ่อม target drift, credential hash ไม่ถูกอ่าน/copy |
| Selective migration | Retail Company/Brand/Branch เท่านั้น; row count/digest exact และ replay exact |
| POS canary | barcode, idempotent sale, full refund, void, stock `20 → 19`, net report `107`, shift close ผ่าน |
| Write isolation | Retail มี sale/payment/movement/outbox; Legacy คง stock `20` และไม่มี canary sale |
| Shared ERP | Retail documents `3`, status completed/refunded/voided และ net sales `107` |
| Rollback route | Platform login + Retail product search จาก Legacy ผ่านแบบ read-only |
| Physical device UAT | พักตามคำสั่ง owner |
| UAT release | commit `df12dcc`; `/`, `/pos`, `/admin`, health และ auto-login ตอบ `200` |
| UAT database boundaries | Legacy `p14dist0016`; Platform `p13platform0017`; Restaurant `p6restaurant0007`; Retail `p8retail0002`; Takeaway `p6takeaway0004` |
| UAT reference parity | Company `1/1`, Branch `2/2`, User `1/1`, Brand `0/0`, BrandBranch `0/0`; mismatch `0` |
| UAT Restaurant data retention | Category `4`, Product `16`, Stock balance `16`, Dining table `16` หลัง cutover |
| UAT backup | before/after dumps ตรวจ SHA-256 และ `pg_restore --list` ผ่าน |
| Retail activation | fail-closed ตามแบบ: UAT มี Retail Brand `0`; คง `RETAIL_SERVICE_DATABASE=legacy` |
| Production | ไม่ deploy, ไม่ migrate และไม่ activate |

| Frontend | type-check และ production/PWA build ผ่าน; `4,206` modules transformed |

คำเตือน large frontend chunk และ test-only JWT/httpx deprecation เป็น warning เดิม ไม่บล็อก local gate

## สิ่งที่ยังบล็อกการเปิดจริง

- scanner, printer, cash drawer และ offline recovery ต้องทดสอบกับอุปกรณ์จริง
- ต้องสร้างหรือเลือก Retail Company/Brand/Branch จริง; UAT ปัจจุบันมี Brand `0`
- ต้องมี Product/Stock Location ที่ผูก Retail Brand ก่อน selective migration
- ต้องตรวจ count/digest/amount/stock กับข้อมูลจริงและ owner ลงนาม
- ต้องมีช่วง cutover, monitoring และ rollback owner ก่อนเปลี่ยน UAT/Production flag

## Rollback หลัก

คืน `RETAIL_SERVICE_DATABASE=legacy` แล้ว restart; Legacy ไม่ถูกลบหรือแก้ระหว่าง selective copy
ส่วน Retail dump/outbox ต้องเก็บไว้เพื่อ audit/reconciliation และห้าม downgrade schema ที่มีข้อมูลจริง

หลักฐาน UAT อยู่ที่ `docs/scopes/WP8-UAT-DARK-LAUNCH-03.md`

งานถัดไปที่ปลอดภัย: สร้าง Retail test tenant ที่มี Brand/Branch/Product/Stock Location ชัดเจน แล้วทำ
selective migration และ parity ใน UAT ก่อนสลับ Retail routing; การเปิด Production ยังต้องกลับมาผ่าน
physical UAT และรายการบล็อกด้านบนก่อน
