# WP44 UAT Deployment and Smoke Report

วันที่: `2026-09-20`
ผล: **PASS — Server-backed Hold Draft UAT engineering gate**
Production: **Unchanged / not approved**

## 1. Release identity

- Repository: `chaiyanutaiagent/restaurant`
- Branch: `codex/foodchainservice-platform`
- Implementation commit: `b72ef3e` — `feat: add server-backed POS hold drafts WP44`
- Accessibility patch: `bfe6e4f` — `fix: describe WP44 hold draft dialog`
- Final UAT release: `wp44-bfe6e4f`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/bfe6e4f`
- Backend image: `restaurant-pos-backend:wp44-bfe6e4f`
- Frontend image: `restaurant-pos-frontend:wp44-bfe6e4f`
- Nginx image: `restaurant-pos-nginx:wp36-41-0ca50c5` (unchanged artifact)
- Migration: `wp44hold0020`

Backend ของ final release เป็น digest เดียวกับ implementation image `wp44-b72ef3e`; final commit เปลี่ยนเฉพาะ
accessible description ของ frontend dialog

## 2. Pre-deploy backup

Backup:

`/home/behappyaiagent/restaurant-uat-deploy-backups/wp44-before/restaurant-pos-uat-20260920T130108Z`

ตรวจแล้ว:

- legacy, Platform, Restaurant, Retail และ Takeaway database dumps เปิด restore catalog ได้ครบ
- Redis และ uploads archives เปิดอ่านได้
- SHA-256 ของทุก artifact และ manifest ผ่าน `sha256sum -c`
- permission ของ backup ปิดเป็น owner-only
- runtime environment `.env.wp8` ก่อนและหลัง WP44 มี SHA-256 เดียวกัน

## 3. Deployment

- build backend/frontend จาก tracked Git archive เท่านั้น
- apply additive migration `wp43price0019 → wp44hold0020`
- recreate เฉพาะ UAT backend/frontend; Nginx, Cloudflare, PostgreSQL และ Redis ใช้ service เดิม
- deploy accessibility patch เป็น immutable final release `wp44-bfe6e4f`
- final backend ผ่าน health check และ public routes `/`, `/pos`, `/admin`, `/health/ready` ตอบ HTTP `200`
- recent UAT HTTP `5xx`: `0`

## 4. Local engineering evidence

- backend full regression `412/412`: ผ่าน, skipped 1
- focused Hold Draft regression `24/24`: ผ่าน
- migration isolated database blank → `wp43price0019` → `wp44hold0020` → downgrade → upgrade: ผ่าน
- TypeScript type-check และ production/PWA build: ผ่าน (`4,233` modules)
- Python compile และ Git whitespace gate: ผ่าน
- non-blocking warning: frontend ยังมี large bundle chunk ซึ่งเป็น performance backlog เดิม

## 5. Final UAT API smoke

Final smoke รันกับ UAT database และ immutable backend image แล้วผ่าน:

- server-authoritative price และไม่เก็บ client payment fields
- Hold ไม่สร้าง Sale, Payment หรือ Stock side effect
- create/claim/resume idempotency และ duplicate-payload protection
- concurrent claim จริงจากสอง thread มีผู้ชนะหนึ่งราย
- optimistic version conflict และ stale response
- cross-staff Branch visibility พร้อม Company/Brand/Branch isolation
- price/stock revalidation และ explicit diff acceptance
- discard reason, expiry/reopen และ append-only audit
- reassign แล้วไม่ block กะเดิม; active draft ยังคง block close shift อย่างถูกต้อง
- resume → Sale conversion เป็น transaction เดียว

ฐาน UAT อยู่ที่ `wp44hold0020` และมี trigger
`trg_pos_hold_draft_audits_append_only` หนึ่งตัว

## 6. Desktop/tablet visual UAT

ตรวจผ่าน public URL `https://uat-pos.foodchainservice.com/pos`:

- เพิ่มสินค้าแล้วกดพักบิลสำเร็จก่อนล้างตะกร้า
- badge เปลี่ยนเป็น `พักบิล 1` และ toast ระบุว่าเรียกต่อได้ทุก Counter
- dialog แสดง `Server-backed · ทุก Counter`, search, filter, owner/history และ touch target ขนาดใหญ่
- Draft `HD20260920-0015` แสดงราคา/จำนวน/version จาก Server และเรียกกลับเข้าตะกร้าได้
- หลังเรียกกลับ cart คืนสินค้า/ราคาเดิม และแจ้งว่าจะตรวจราคาอีกครั้งตอนชำระ
- layout ผ่านทั้ง desktop และ tablet landscape `1024×768`
- accessibility warning ของ dialog ถูกแก้ใน `bfe6e4f`; asset ใหม่ `index-C2tE2IEN.js` ไม่มี console warning/error

Draft ที่ใช้ visual UAT อยู่ในสถานะ `resumed` ซึ่งเป็นประวัติ UAT, ไม่สร้างการชำระเงิน การขาย หรือผลต่อสต๊อก
และไม่ block การปิดกะ

## 7. Runtime boundaries

| Setting | Final UAT value | WP44 action |
| --- | --- | --- |
| Identity database | `platform_core` | ไม่เปลี่ยน |
| Restaurant service database | `legacy` | ไม่เปลี่ยน |
| Retail service database | `retail` | ไม่เปลี่ยน source |
| Takeaway service database | `takeaway` | ไม่เปิด transaction ใหม่ |
| Takeaway feature | `true` | คง dark-launch state เดิม |
| Central Kitchen writes | `false` | ไม่เปิด |
| Company Distribution writes | `false` | ไม่เปิด |

ไม่มีการสร้าง/ยื่นเอกสารภาษีจริง และไม่มี Production flag ถูกเปิด

## 8. Rollback readiness

- previous release `/home/behappyaiagent/restaurant-uat-releases/6b7b0c6` และ WP43 images ยังอยู่
- application rollback ถูกพิสูจน์จริง: สลับ backend/frontend กลับ `wp43-6b7b0c6` บน schema WP44 แล้ว health ผ่าน,
  จากนั้นสลับกลับ WP44 และรัน smoke ซ้ำผ่าน
- migration เป็น additive; old application ใช้ schema ใหม่ได้ใน application-first rollback
- schema downgrade กลับ `wp43price0019` ผ่าน isolated rehearsal
- restore backup ใช้เฉพาะเมื่อ reconciliation พบ data effect ผิดพลาด

## 9. Production verification

Production container IDs และ image tags ก่อน/หลัง WP44 ตรงกันทุกตัว ไม่มี service ถูก restart, migrate หรือ deploy

## 10. Residual blockers

- Loyalty redemption ยังต้องเปลี่ยนเป็น reserve → commit/release แบบ idempotent ก่อน Production
- polling รายการพักบิลทุก 15 วินาทียังไม่ใช่ realtime websocket
- offline shadow conflict ต้องให้ผู้ใช้ตรวจ ไม่ให้ Local ชนะ Server อัตโนมัติ
- Physical UAT เครื่องพิมพ์ เงินสด PromptPay, paired Counter/iPad และกรณีเน็ตหลุดยังอยู่ใน WP47

## 11. Decision

WP44 ผ่าน Local/UAT engineering gate และปิดในขอบเขต UAT เท่านั้น Production ยังคงไม่อนุมัติ
และยังไม่เริ่ม WP45
