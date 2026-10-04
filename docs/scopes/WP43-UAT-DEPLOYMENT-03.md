# WP43 UAT Deployment and Smoke Report

วันที่: `2026-09-20`
ผล: **PASS — Server-Authoritative Price and Price Override UAT engineering gate**
Production: **Unchanged / not approved**

## 1. Release identity

- Repository: `chaiyanutaiagent/restaurant`
- Branch: `codex/foodchainservice-platform`
- Implementation commit: `c8aa90b` — `feat: enforce server-authoritative POS pricing WP43`
- Boundary correction commits:
  - `df1aeec` — trial correction rejected by UAT because grant usage belongs to Operational DB
  - `51a6f5d` — restored the correct operational grant-consumption boundary
  - `6b7b0c6` — final UAT boundary/offline smoke coverage
- Final UAT release: `wp43-6b7b0c6`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/6b7b0c6`
- Backend image: `restaurant-pos-backend:wp43-6b7b0c6`
- Frontend image: `restaurant-pos-frontend:wp43-6b7b0c6`
- Nginx image: `restaurant-pos-nginx:wp36-41-0ca50c5` (unchanged artifact)
- Migration: `wp43price0019`

## 2. Pre-deploy backup

Backup:

`/home/behappyaiagent/restaurant-uat-deploy-backups/wp43-before/restaurant-pos-uat-20260920T113025Z`

ตรวจแล้ว:

- legacy, Platform, Restaurant, Retail และ Takeaway database dumps เปิด catalog ได้
- Redis และ uploads archives อ่านได้
- SHA-256 ของทุก artifact ถูกคำนวณและเก็บเป็นหลักฐาน
- runtime environment `.env.wp8` ของ WP42 และ final WP43 มี SHA-256 เดียวกัน

## 3. Deployment

- build backend/frontend จาก tracked Git archive เท่านั้น
- apply additive migration จาก `p16taxops0018` เป็น `wp43price0019`
- recreate เฉพาะ UAT backend/frontend/nginx; Cloudflare, Redis และ Production ไม่ถูกเปลี่ยน
- PostgreSQL UAT ถูก recreate โดย Docker Compose ระหว่าง migration runner แต่ใช้ named volume เดิม,
  ผ่าน health check และข้อมูลคงอยู่ครบ
- final backend และ PostgreSQL/Redis ผ่าน health check

## 4. Local engineering evidence

- backend full regression `408/408`: ผ่าน
- focused pricing/approval/role tests `24/24`: ผ่าน
- TypeScript type-check: ผ่าน
- production/PWA build: ผ่าน (`4,233` modules)
- Python compile และ Git whitespace gate: ผ่าน
- migration blank → head → downgrade `p16taxops0018` → head: ผ่าน
- append-only database trigger: ผ่าน
- non-blocking warning: frontend ยังมี large bundle chunk ซึ่งเป็น performance backlog เดิม

## 5. Final UAT smoke

Final smoke รันจาก immutable release `6b7b0c6` และผ่าน:

- client price/VAT tampering ไม่เปลี่ยน server total
- VAT/discount/rounding และ authoritative snapshot
- Price Override threshold, manager approval และ separation of duties
- approval token ผูก context/request และ grant ใช้ซ้ำไม่ได้
- idempotent replay ไม่สร้าง order/payment/stock effect ซ้ำ
- duplicate payload, context mismatch, stale price และ cart version conflict
- Restaurant offline checkout ถูก reject ด้วย `stale_price`
- override audit แก้ไขย้อนหลังไม่ได้
- order/payment/stock reconciliation หลังสอง sale ถูกต้อง

Public/live checks:

- `/`, `/pos`, `/admin`, `/health/ready`: HTTP `200` ทั้ง local UAT proxy และ public HTTPS routes ที่เกี่ยวข้อง
- recent UAT nginx HTTP `5xx`: `0`
- schema head: `wp43price0019`
- trigger: `trg_price_override_audits_append_only`

## 6. Boundary correction found by UAT

UAT แยก Platform Identity DB และ Restaurant Operational DB ต่างจาก local test แบบฐานเดียว ทำให้ smoke
ตรวจพบว่าการแก้ชั่วคราวให้ consume approval grant ใน Identity DB ไม่ถูกต้อง เพราะ
`approval_grant_usages` อยู่ Operational DB โดยตั้งใจ

การตอบสนอง:

1. rollback UAT backend จาก trial image กลับ `wp43-c8aa90b`; health ผ่าน
2. คืน flow ที่ถูกต้อง: Manager PIN/การออก token อยู่ Platform ส่วน signed token และ unique grant usage
   ถูกตรวจ/consume ใน transaction เดียวกับ sale ที่ Operational DB
3. เพิ่ม fixture projection สำหรับ Platform → Restaurant/Retail และรัน smoke ใหม่จนผ่าน

trial commit `df1aeec` จึงถูก supersede โดย `51a6f5d`; final release ไม่มี behavior ที่ผิด boundary

## 7. Runtime boundaries

| Setting | Final UAT value | WP43 action |
| --- | --- | --- |
| Identity database | `platform_core` | ไม่เปลี่ยน |
| Restaurant service database | `legacy` | ไม่เปลี่ยน |
| Retail service database | `retail` | ไม่เปลี่ยน source |
| Takeaway service database | `takeaway` | ไม่เปลี่ยน/ไม่เปิด transaction ใหม่ |
| Takeaway feature | `true` | คง dark-launch state เดิม |
| Central Kitchen writes | `false` | ไม่เปิด |
| Company Distribution writes | `false` | ไม่เปิด |

ไม่มีการสร้าง/ยื่นเอกสารภาษีจริง และไม่มี Production flag ถูกเปิด

## 8. Rollback readiness

- previous release `/home/behappyaiagent/restaurant-uat-releases/2988072` ยังอยู่
- previous images ยังอยู่:
  - backend `restaurant-pos-backend:wp36-41-0ca50c5`
  - frontend `restaurant-pos-frontend:wp42-2988072`
  - nginx `restaurant-pos-nginx:wp36-41-0ca50c5`
- application rollback ถูกพิสูจน์จริงระหว่าง boundary correction และ health ผ่าน
- migration เป็น additive; old application ใช้กับ schema ใหม่ได้ใน application-first rollback
- schema downgrade ผ่าน isolated rehearsal; restore backup เฉพาะเมื่อ reconciliation ชี้ว่าจำเป็น

## 9. Production verification

Production container IDs และ image tags ก่อน/หลัง WP43 ตรงกันทุกตัว ไม่มี service ถูก restart หรือ deploy

## 10. Residual blocker

Loyalty redemption เดิมยัง consume แต้มก่อน sale commit แม้ WP43 รวม loyalty discount ใน authoritative
discount calculation และเตือนผู้ใช้เมื่อ checkout ล้มเหลวแล้ว ต้องทำ reserve → commit/release ผูกกับ
`client_order_id` ก่อน Production

## 11. Decision

WP43 ผ่าน Local/UAT engineering gate และพร้อมปิดในขอบเขต UAT เท่านั้น Production ยังคงไม่อนุมัติ
และยังไม่เริ่ม WP44
