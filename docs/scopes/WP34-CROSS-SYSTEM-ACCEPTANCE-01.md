# WP34 — Cross-System Security, Recovery and Acceptance

วันที่: `2026-09-18`
สถานะ: **engineering_ready — physical defect acceptance pending**

## Security and automated acceptance

| Gate | ผล |
| --- | --- |
| Full backend regression | `386` tests ผ่าน (`1` optional skip) |
| Cross-boundary security focused regression | `54/54` ผ่าน |
| Platform/Company/browser workspace suite | รวมใน browser candidate `26/26` ผ่าน |
| Restaurant load/reconnect/idempotency | `100` orders ผ่าน |
| Takeaway secret/DB-boundary scan | ผ่าน |
| Repository safety | ไม่มี secret/certificate/dump ใน Git-visible path; local backups ถูก ignore และ untracked |
| Backend dependency audit | ไม่พบ known vulnerability |
| Frontend critical dependency finding | `0`; reviewed production/dev-tool exceptions คงบันทึกแยก |

## Fresh five-boundary recovery evidence

Backup timestamp: `2026-09-18T07:29:35Z`

- Server: `/home/behappyaiagent/restaurant-cutover-backups/wp34-candidate/restaurant-pos-prod-20260918T072935Z`
- Mac rollback copy: `backups/wp34-candidate/` (ignored, untracked, ขนาดประมาณ `1.6 MB`)
- เนื้อหา: Legacy, Platform Core, Restaurant, Retail, Takeaway, uploads และ Redis
- checksum ของ dump ทั้ง 5 ไฟล์ตรงกับ manifest หลังคัดลอกลง Mac
- restore เข้า isolated temporary databases ทั้ง 5 ขอบเขตผ่าน
- migration head ของ Legacy และ boundary metadata ของอีก 4 ฐานตรงตามคาด
- temporary drill databases ถูกลบหลังตรวจ; live source databases ไม่ถูก restore หรือเขียนทับ

## Production observation หลัง backup/drill

- backend/frontend/nginx/postgres/redis/cloudflared running และ restart count `0`
- backend `/health` และ `/health/ready` ตอบ `200`
- public root และ public readiness ตอบ `200`
- backend critical/traceback/fatal ในหนึ่งชั่วโมง: `0`
- Nginx HTTP 5xx ในหนึ่งชั่วโมงและสิบนาทีล่าสุด: `0`

หมายเหตุ: backup command ทำให้ PostgreSQL container ถูก recreate หนึ่งครั้งโดยใช้ volume เดิม;
หลังเริ่มใหม่ฐานตอบ query และ health ทุกชั้นผ่าน ไม่มี application container restart

## External acceptance ที่ยังไม่สมมติผล

- [ ] defect triage จาก Restaurant iPad/printer/payment pilot
- [ ] Retail scanner/printer/cash drawer/offline acceptance
- [ ] Central Kitchen opening-lot/physical-count acceptance
- [ ] Takeaway approved snapshot/tablet/printer/canary acceptance
- [ ] Accountant/tax acceptance และ Platform operator MFA
- [ ] owner ตัดสินใจรับความเสี่ยง dependency exception และ residual defects

## Decision

ระบบผ่าน engineering recovery/security gate และมี rollback copy ทั้ง server/Mac แต่ WP35 ต้องคงสถานะ
`no-go` สำหรับ activation ที่ยังไม่มี physical/owner evidence
