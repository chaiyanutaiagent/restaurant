# WP82 — UAT Live Transaction Activation

วันที่: 2026-09-27

สถานะ: **ACTIVE — UAT ONLY; persistent internal transactions enabled**

## ขอบเขตที่เปิดใช้งาน

- Restaurant POS และ Retail POS คง write path ที่เปิดใช้งานอยู่แล้ว
- เปิด `TAKEAWAY_UAT_TRANSACTION_WRITES_ENABLED=true`
- เปิด `COMPANY_KITCHEN_WRITES_ENABLED=true`
- เปิด `COMPANY_DISTRIBUTION_WRITES_ENABLED=true`
- Takeaway, ครัวกลาง และ Distribution สามารถบันทึกธุรกรรมลงฐานข้อมูล UAT จริง
- คง `ENVIRONMENT=development` และ `REFUND_PROVIDER_MODE=sandbox`
- ไม่เปิด Production, live payment/refund provider หรือเอกสารภาษีจริง

## Deployment evidence

- Backend image: `restaurant-pos-backend:wp81-78aee14`
- Frontend image: `restaurant-pos-frontend:wp81-78aee14`
- Backend health: `healthy`
- Runtime image variables ถูกตรึงเป็น WP81 เพื่อป้องกันการ restart แล้วย้อนกลับไป release เก่า
- Restart เฉพาะ UAT backend; Production และ UAT PostgreSQL/Redis/Nginx/Cloudflare Tunnel/Frontend มี container identity เดิม
- HTTP `200`: Company, Restaurant POS, Retail POS, Takeaway sale และ Takeaway fulfillment

## Persistent transaction proof

- Takeaway order: `TW-20260923-1F3972-0088`
- Order ID: `0e637a69-ec61-490a-8bf6-0f18173d5c0b`
- Payment: เงินสด `35.31` บาท รวม VAT; สถานะ `paid`
- Fulfillment: `queued -> preparing -> ready -> picked_up`
- Stock movement บันทึกผ่าน API และยอดขายตัดสต๊อกคลังหน้าร้านจริง
- Stock consolidation transfer: `TT-20260927-0004`, สถานะ `received`
- เมนูที่พร้อมขายจากคลังหลัก `13/14`; อีก `1` เมนูมีสถานะหมดตามยอดจริง

รายการข้างต้นเป็นข้อมูลทดสอบ UAT ที่จงใจเก็บไว้เพื่อให้ผู้ทดสอบตรวจสอบรายงาน ยอดขาย เงินสด สต๊อก และ audit trail ได้

## Rollback

- Pre-activation backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/wp82-before-live-uat-transactions-0c0302e`
- สำรอง `.env.uat` และ custom-format dump ครบ 5 ฐานข้อมูล
- SHA-256 verification และ `pg_restore --list` ผ่านทั้งหมด
- การ rollback ฐานข้อมูลต้องได้รับคำสั่งแยก เพราะจะลบธุรกรรม UAT ที่บันทึกหลัง activation

## UAT boundary

- ธุรกรรมที่ผู้ทดสอบสร้างหลังจากนี้จะคงอยู่จริงในฐานข้อมูล UAT และปรากฏในรายงาน
- ใช้ชื่อ/เบอร์/ข้อมูลชำระเงินทดสอบเท่านั้น
- PromptPay, payment provider, refund provider และภาษีภายนอกใช้ sandbox/synthetic เท่านั้น
- Production hostname, Production database และ Production containers ไม่ได้รับการเปลี่ยนแปลง
