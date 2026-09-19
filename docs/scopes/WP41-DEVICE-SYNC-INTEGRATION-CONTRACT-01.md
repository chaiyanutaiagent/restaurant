# WP41 — Device, Sync and Integration State Contract

วันที่: `2026-09-19`
สถานะ: **Implemented locally — Production unchanged**

## Outcome

เพิ่ม `GET /api/v1/company/operational-status` และ state กลาง:

`online`, `offline`, `degraded`, `pending_sync`, `stale`, `error`, `disabled`

Contract ของ component มี `last_seen_at`, `last_sync_at`, queue size, error code, retryability,
source system, Company/Branch/Station scope และ updated time ครอบคลุม device registry, webhook,
payment configuration, Retail data source และ shared reporting projector

Device threshold ปัจจุบัน: ภายใน 2 นาทีเป็น online, 2–15 นาทีเป็น degraded, เกิน 15 นาทีเป็น stale,
ยังไม่ pair/ไม่เคย seen เป็น offline และ revoked เป็น disabled

Company Audit endpoint รวม identity และ operational audit stream เมื่อแยกฐานข้อมูล โดยยังแยกจาก
Platform Audit และกรองตาม Company/Branch scope เสมอ

WP นี้ไม่อ้างว่า offline queue reconciliation ทุกผลิตภัณฑ์เสร็จสมบูรณ์; API แสดงสถานะจริงและ fail closed
เพื่อให้ UI ออกแบบ error/offline/retry state ได้อย่างถูกต้อง
