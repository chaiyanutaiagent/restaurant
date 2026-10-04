# WP46 UAT Deployment and Smoke Report

วันที่: `2026-09-20`
ผล: **PASS — Provider Refund + Tax/Credit Note UAT engineering gate**
Production: **Unchanged / not approved**

## 1. Release identity

- Repository: `chaiyanutaiagent/restaurant`
- Branch: `codex/foodchainservice-platform`
- Implementation commit: `0da47bf` — `feat: add provider refund and UAT credit note WP46`
- Test/config commit: `062532e` — `test: use configured UAT refund webhook secret`
- Accessibility commit: `4c6c1a9` — `fix: describe recent sales refund dialog`
- Final UAT release: `wp46-4c6c1a9`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/4c6c1a9`
- Backend image: `restaurant-pos-backend:wp46-4c6c1a9`
- Backend digest: `sha256:ff2fdd41c6f12ad87b0661d7293a110ccabbb802428d3c0701240a2e76b428f3`
- Frontend image: `restaurant-pos-frontend:wp46-4c6c1a9`
- Frontend digest: `sha256:02a0a6cc1d574c9ab933694c1bcc642d5cbef20661c0cf60e90b270fd834f933`
- Nginx image: `restaurant-pos-nginx:wp36-41-0ca50c5` (unchanged artifact)
- Migration: `wp46refund0022`

Backend final tag ใช้ digest เดียวกับ implementation image; accessibility commit เปลี่ยนเฉพาะ frontend
description ของ Recent Sales dialog

## 2. Pre-deploy backup

Backup:

`/home/behappyaiagent/restaurant-uat-deploy-backups/wp46-before/restaurant-pos-prod-20260920T155655Z`

ตรวจแล้ว:

- logical dumps ของ legacy, Platform, Restaurant, Retail และ Takeaway เปิด restore catalog ได้
- Redis และ uploads archives เปิดอ่านได้
- checksum ของ database dumps, Redis และ uploads ผ่านครบทุกไฟล์
- เก็บ Production/UAT container identity ก่อน deploy ไว้ในชุดเดียวกัน

ชื่อ directory ภายใน artifact ใช้คำว่า `prod` ตามชื่อ snapshot utility เดิม แต่หลักฐานชุดนี้ถูกใช้เป็น
UAT pre-deploy rollback evidence; ไม่มีการ restore หรือแก้ Production

## 3. Deployment

- build จาก tracked Git archive ของ commit ที่ระบุเท่านั้น
- apply additive migration `wp45cancel0021 → wp46refund0022`
- เปิดเฉพาะ UAT sandbox provider และ synthetic `UAT NON-FISCAL` Credit Note
- `POS_OFFLINE_MODE_ENABLED=false`; WP47 ยังเป็น design/test plan เท่านั้น
- recreate เฉพาะ UAT backend/frontend; PostgreSQL, Redis, Nginx และ Cloudflare service เดิม
- backend healthy และ public HTTPS routes `/`, `/pos`, `/admin`, `/health/ready` ตอบ HTTP `200`
- recent UAT HTTP `5xx`: `0`

## 4. Local engineering evidence

- backend regression `432/432`: ผ่าน, skipped `1`
- WP46/WP47 targeted contract tests `10/10`: ผ่าน
- migration isolated blank/state rehearsal `wp45cancel0021 → wp46refund0022 → downgrade → upgrade`: ผ่าน
- TypeScript type-check และ production/PWA build: ผ่าน (`4,234` modules)
- Python compile และ Git whitespace gate: ผ่าน
- non-blocking warning: frontend ยังมี large bundle chunk ซึ่งเป็น performance backlog เดิม

## 5. Final UAT API smoke

Final smoke รันกับ UAT database และ immutable backend image แล้วผ่าน:

- Server-authoritative quote, VAT, split tender allocation และ exact-payload maker-checker
- idempotency/replay และ concurrent stale quote ป้องกัน over-refund
- cash confirmation และ close-shift blocker
- provider success/failure/unknown/inquiry/retry โดย unknown ไม่มี financial side effect
- signed webhook, duplicate replay, same-id/different-payload rejection และ out-of-order guard
- negative Payment ledger exactly-once, stock disposition และ loyalty earned-points reversal
- redeemed-points refund fail closed จนมี atomic reserve/restore contract
- synthetic non-fiscal Credit Note หลัง refund success เท่านั้น
- reconciliation, append-only audit และ immutable Credit Note
- legacy immediate-refund endpoints ปิดด้วย HTTP `410`

การทดสอบผ่าน browser รอบสุดท้ายสร้างเฉพาะ refund quote; ไม่ได้ยืนยัน approval และไม่เกิดเงินจริง/ledger/stock/tax mutation

## 6. Desktop/tablet visual UAT

ตรวจผ่าน `https://uat-pos.foodchainservice.com/pos`:

- POS และ Recent Sales ทำงานที่ Desktop/iPad landscape `1024×768`
- Refund Workspace แสดงยอดคืน, ก่อน VAT, VAT, payment allocation, provider state และ stock disposition
- maker-checker dialog แยกผู้ขอ/ผู้อนุมัติ พร้อมคำอธิบาย approval แบบใช้ครั้งเดียว
- touch target หลักของ workflow อยู่ที่อย่างน้อย `44px`
- Recent Sales dialog มี accessible description และ browser console รอบสุดท้ายไม่มี warning/error
- viewport ถูก reset และปิดแท็บทดสอบหลังจบงาน

## 7. Runtime boundaries

| Setting | Final UAT value | Boundary |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | UAT only |
| `REFUND_PROVIDER_MODE` | `sandbox` | no live provider |
| `REFUND_UAT_NON_FISCAL_CREDIT_NOTE_ENABLED` | `true` | not submitted / non-fiscal |
| `POS_OFFLINE_MODE_ENABLED` | `false` | design only |
| Retail data source | unchanged | no cutover |
| Takeaway/Central Kitchen writes | unchanged gated state | not opened |

ไม่มี live provider call, เอกสารภาษีจริง หรือ Production feature flag ถูกเปิด

## 8. Rollback readiness

- previous WP45 images ยังอยู่และ backup ก่อน deploy ผ่าน integrity check
- application-first rollback ไป `restaurant-pos-backend:wp45-600c6d4` และ
  `restaurant-pos-frontend:wp45-600c6d4` บน additive WP46 schema ผ่าน
- public routes และ backend health ผ่านระหว่าง rollback
- measured rollback RTO: `9 seconds`
- restore กลับ WP46 แล้วรัน final API smoke ซ้ำผ่าน
- schema downgrade/upgrade ผ่าน isolated rehearsal
- data restore ใช้เฉพาะเมื่อ reconciliation ยืนยัน corruption และต้องได้รับอนุมัติแยก

## 9. Production verification

Production container IDs และ image tags ก่อน/หลัง WP46 ตรงกันทุกตัว:

| Service | Image | Container ID |
| --- | --- | --- |
| Backend | `restaurant-pos-backend:auth-a0fdccf` | `f6e08435721a` |
| Frontend | `restaurant-pos-frontend:ui-e4200ca` | `857e0dbab1a2` |
| Nginx | `restaurant-pos-nginx:unified-d528512` | `aea97e7f90f7` |
| Cloudflared | `cloudflare/cloudflared:2026.7.0` | `ae6862f8a09f` |
| PostgreSQL | `postgres:15-alpine` | `3565e3fd72ad` |
| Redis | `redis:7-alpine` | `76658d7ad2fd` |

ไม่มี Production service ถูก restart, migrate หรือ deploy

## 10. Residual blockers

- real provider credential/webhook/inquiry/SLA และ security review
- Accountant/Tax Owner sign-off สำหรับเลขเอกสาร, partial Credit Note, XML/submission และงวดบัญชี
- atomic loyalty redeem reserve/restore
- Physical UAT เครื่องพิมพ์ เงินสด PromptPay, paired Counter/iPad และกรณีเน็ตหลุด
- WP47 Offline/Sync implementation, encrypted local storage, outbox reconciliation และ rollback evidence
- Production owner approval และ deployment gate แยกต่างหาก

## 11. Decision

WP46 ผ่าน Local/UAT engineering gate และปิดในขอบเขต UAT เท่านั้น ระบบยังไม่ Production-ready
และงานถัดไปคือ Physical UAT/WP47 โดยคง offline flag ปิดจนกว่าจะผ่าน gate

