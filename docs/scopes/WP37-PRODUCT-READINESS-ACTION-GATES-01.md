# WP37 — Product Readiness and Action Gates

วันที่: `2026-09-19`
สถานะ: **Implemented locally — Existing server gates preserved**

## Outcome

Module Access กลางรองรับสถานะ `production`, `pilot`, `dark_launch`, `read_only`, `legacy` และ
`planned` พร้อม environment, allowed actions, branch scope, feature flags, data source, ผู้เปลี่ยนล่าสุด,
เวลาและเหตุผลจาก audit เดิม

สถานะเริ่มต้นตามมติ CTO:

| Module | Readiness | Write behavior |
| --- | --- | --- |
| ERP | production | ตาม permission/approval เดิม |
| Restaurant POS | pilot | ตาม permission และ runtime gate |
| Retail POS | pilot หรือ legacy ตาม data source | แสดง source จริง |
| Takeaway | dark_launch | ไม่คืน action จน runtime และ tenant gate ผ่าน |
| Central Kitchen | read_only | คืนเฉพาะ view/export จน write gates ทั้งคู่เปิด |
| Hotel PMS | planned | ไม่คืน action |

Backend gate เดิมของ Takeaway และ Central Kitchen ยังคงเป็นผู้ตัดสินธุรกรรมจริง UI ไม่ใช่ security
control และไม่มีการเปิด Production flag ใน WP นี้
