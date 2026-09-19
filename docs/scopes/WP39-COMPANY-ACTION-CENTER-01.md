# WP39 — Unified Company Action Center

วันที่: `2026-09-19`
สถานะ: **Implemented locally — Read model over existing workflows**

## Outcome

เพิ่ม `GET /api/v1/company/action-center` เพื่อรวมงานตามสิทธิ์จาก:

- คำขอสิทธิ์พนักงาน
- ใบสั่งซื้อรออนุมัติ
- การโอนสินค้ารออนุมัติ
- ประเด็น tax reconciliation
- notification delivery ที่ pending/failed/error

รายการมี stable id, source app, severity, scope, owner, status, required permission, available actions,
deep link, unread และ business impact แล้วเรียงแบบคงที่ตาม severity > impact > due/created time > id

การ assign/acknowledge/dismiss บันทึก Audit Log ผ่าน
`POST /api/v1/company/action-center/{work_item_id}/actions` ส่วน approve/return/complete ที่เปลี่ยน
ธุรกรรมจริงยังคงทำใน source module เพื่อรักษา maker-checker, idempotency และ domain validation เดิม

Frontend เพิ่ม `/company/actions`; การซ่อนรายการเป็นสถานะส่วนผู้ใช้และไม่เปลี่ยนเอกสารต้นทาง
