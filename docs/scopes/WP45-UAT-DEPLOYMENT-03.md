# WP45 UAT Deployment and Smoke Report

วันที่: `2026-09-20`
ผล: **PASS — Restaurant Cancellation Approval + Waste/Audit UAT engineering gate**
Production: **Unchanged / not approved**

## 1. Release identity

- Repository: `chaiyanutaiagent/restaurant`
- Branch: `codex/foodchainservice-platform`
- Implementation commit: `4fc67a7` — `feat: add restaurant cancellation governance WP45`
- Accessibility patch: `600c6d4` — `fix: describe WP45 cancellation dialog`
- Final UAT release: `wp45-600c6d4`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/600c6d4`
- Backend image: `restaurant-pos-backend:wp45-600c6d4`
- Backend digest: `sha256:0a81f7e06c0e57235c682562f3ecbe3d0bdfea9f5394963b3691c95f39f41352`
- Frontend image: `restaurant-pos-frontend:wp45-600c6d4`
- Frontend digest: `sha256:d9ea262758c0ce67bd050129b599daa9e22e631d9b813d948145514f2d0808f6`
- Nginx image: `restaurant-pos-nginx:wp36-41-0ca50c5` (unchanged artifact)
- Migration: `wp45cancel0021`

Backend final tag ใช้ digest เดียวกับ implementation tag `wp45-4fc67a7`; accessibility patch เปลี่ยนเฉพาะ
accessible description ของ frontend cancellation dialog

## 2. Pre-deploy backup

Backup:

`/home/behappyaiagent/restaurant-uat-deploy-backups/wp45-before/restaurant-pos-prod-20260920T142040Z`

ตรวจแล้ว:

- logical legacy, Platform, Restaurant, Retail และ Takeaway database dumps เปิด restore catalog ได้ครบ
- Redis และ uploads archives เปิดอ่านได้
- SHA-256 ของทุก artifact และ manifest ผ่าน `sha256sum -c`
- permission ของ backup directory เป็น owner-only และไฟล์เป็น owner read/write
- เก็บ Production และ UAT container identity ก่อน deploy ไว้ใน backup ชุดเดียวกัน

ชื่อ directory ภายใน artifact ใช้คำว่า `prod` ตามชื่อสคริปต์ snapshot เดิม แต่ข้อมูลที่ใช้ rollback งานนี้คือ
UAT pre-deploy snapshot; ไม่มีการ restore หรือเปลี่ยน Production

## 3. Deployment

- build backend/frontend จาก tracked Git archive ของ commit ที่อนุมัติเท่านั้น
- apply additive migration `wp44hold0020 → wp45cancel0021`
- recreate เฉพาะ UAT backend/frontend เพื่อ deploy final application
- ระหว่าง migration, Compose recreate UAT PostgreSQL container เพราะ config hash/release path เปลี่ยน แต่ใช้ data volume เดิม
- หลัง recreate ตรวจพบ service databases ครบ 5 ชุดและไม่มีข้อมูลสูญหาย
- Nginx, Cloudflare และ Redis ใช้ UAT service เดิม
- final backend healthy และ public routes `/`, `/pos`, `/admin`, `/health/ready` ตอบ HTTP `200`
- recent UAT HTTP `5xx`: `0`

## 4. Local engineering evidence

- backend full regression `422/422`: ผ่าน, skipped 1
- migration isolated database blank → `wp44hold0020` → `wp45cancel0021` → downgrade → upgrade: ผ่าน
- TypeScript type-check และ production/PWA build: ผ่าน (`4,233` modules)
- Python compile และ Git whitespace gate: ผ่าน
- non-blocking warning: frontend ยังมี large bundle chunk ซึ่งเป็น performance backlog เดิม

## 5. Final UAT API smoke

Final smoke รันกับ UAT database และ immutable backend image แล้วผ่าน:

- pending cancellation ไม่ต้องอนุมัติและไม่สร้าง Waste
- cooking/done cancellation บังคับ Manager คนละคนกับผู้ขอและตัด Waste เต็มตามสูตร
- served และ post-checkout cancellation fail closed ไป Comp/Refund flow
- missing recipe, missing stock mapping และ stock shortage fail closed ทั้ง transaction
- cancellation receipt, Waste, audit และ KDS event อยู่ใน transaction เดียว
- KDS acknowledge/replay และ Company/Brand/Branch/Station isolation
- idempotency, canonical payload protection, optimistic row version และ concurrent one-winner
- reopen ผ่าน Manager approval สร้าง order/ticket ใหม่ด้วยราคาปัจจุบัน โดยไม่ย้อน Waste เดิม
- ไม่มี Sale, Payment, Refund, Tax document หรือ Credit Note side effect

ฐาน UAT อยู่ที่ `wp45cancel0021` และมี append-only database trigger ครบ 3 ตัวสำหรับ
Cancellation receipt, Waste และ Cancellation audit

## 6. Desktop/tablet visual UAT

ตรวจผ่าน public URL `https://uat-pos.foodchainservice.com`:

- Session แสดงรายการ active/cancelled, ประวัติการยกเลิก และ action เปิดเป็นออเดอร์ใหม่
- dialog แสดง kitchen stage, bill impact, Waste policy, Manager approval และ structured reasons
- stock shortage แสดงจำนวนที่มี/ต้องใช้, fail closed และปิดปุ่มขออนุมัติ
- KDS แสดง cancellation event สีแดงแยก station พร้อมปุ่มรับทราบขนาดเหมาะกับการสัมผัส
- layout ผ่านทั้ง desktop และ tablet landscape `1024×768`
- final frontend asset `index-CCiYUvZU.js` ไม่มี console warning/error หลังเปิด cancellation dialog
- context ของ browser ทดสอบถูกคืนไปที่ `Test Company / สาขากรุงเทพ` หลังจบงาน

ข้อมูล `Approval Smoke` เป็นข้อมูล UAT สำหรับพิสูจน์ lifecycle/audit เท่านั้น ไม่สร้างการชำระเงิน
เอกสารภาษี หรือผลกระทบ Production

## 7. Runtime boundaries

| Setting | Final UAT value | WP45 action |
| --- | --- | --- |
| Identity database | `platform_core` | ไม่เปลี่ยน |
| Restaurant service database | `legacy` | ไม่เปลี่ยน |
| Retail service database | `retail` | ไม่เปลี่ยน source |
| Takeaway service database | `takeaway` | ไม่เปิด transaction ใหม่ |
| Takeaway/Central Kitchen writes | existing gated state | ไม่เปิด |
| Refund/Tax/Credit Note | not implemented in WP45 | ไม่เปิด |

ไม่มีการสร้าง/ยื่นเอกสารภาษีจริง และไม่มี Production flag ถูกเปิด

## 8. Rollback readiness

- previous WP44 images ยังอยู่และ backup ก่อน deploy ผ่าน integrity check
- application-first rollback ถูกพิสูจน์จริงด้วย image ที่ pin ชัดเจน:
  `restaurant-pos-backend:wp44-bfe6e4f` และ `restaurant-pos-frontend:wp44-bfe6e4f`
- WP44 application ทำงานบน additive WP45 schema ได้; public routes ผ่านและ backend healthy
- measured rollback RTO: `12 seconds`
- สลับกลับ WP45 แล้วรัน final API smoke ซ้ำผ่าน
- schema downgrade กลับ `wp44hold0020` ผ่าน isolated rehearsal
- restore backup ใช้เฉพาะเมื่อ reconciliation พบ data corruption และต้องได้รับอนุมัติแยกต่างหาก

ไฟล์ environment ของ release เก่าอาจมี image metadata ค้าง จึงห้ามใช้เป็น rollback evidence โดยไม่ตรวจ tag;
runbook ที่ยืนยันแล้วต้อง pin backend/frontend image variables แบบ explicit ทุกครั้ง

## 9. Production verification

Production container IDs และ image tags ก่อน/หลัง WP45 ตรงกันทุกตัว:

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

- provider refund, return stock, Tax/Credit Note และ real tax document อยู่ใน WP46
- loyalty reserve → commit/release ยังต้อง atomic กับ Sale ก่อน Production
- Physical UAT เครื่องพิมพ์ เงินสด PromptPay, paired Counter/iPad และ network-loss workflow อยู่ใน WP47
- Production ต้องมี owner approval และ deployment gate แยกต่างหาก

## 11. Decision

WP45 ผ่าน Local/UAT engineering gate และปิดในขอบเขต UAT เท่านั้น Production ยังคงไม่อนุมัติ
และยังไม่เริ่ม WP46
