# WP23 — Takeaway Simulation / Regression

วันที่: 2026-09-17

สถานะ: **automated gate completed — physical UAT ยังไม่ถูกนับรวม**

## Journey ที่พิสูจน์แล้ว

- Paid-first sale, stock posting, receipt และ shift cash reconciliation
- Offline client ID / lost acknowledgement replay ส่งซ้ำแล้วคืน order เดิม ไม่เกิดบิลหรือ stock movement ซ้ำ
- Customer QR order รอชำระก่อนสร้าง KDS ticket, payment replay ไม่เกิดรายการซ้ำ
- KDS queued → preparing → ready, Pickup → picked up และ public status
- Central regular/unlisted order, approve/produce/pack/ship/receive
- วัตถุดิบกองกลางหนึ่งยอดถูกใช้ผลิตสินค้าคนละแบรนด์โดยยอดคงเหลือถูกต้อง
- Production, transfer, credit ledger และ ERP acknowledge replay
- Refund rollback คืน stock ไป location เดิม
- Synthetic import รอบสองคืน batch เดิม, opening stock/credit ตรง และ history ไม่สร้าง side effect
- Company Owner, Brand Manager, Branch Manager, Cashier และ Kitchen Staff มีขอบเขต Takeaway ตามหน้าที่
- Shared reporting คง dimension แยก `restaurant_pos`, `retail_pos`, `takeaway_pos`

## ผลตรวจรอบนี้

- Backend regression: 382 tests ผ่าน, skipped 1
- Takeaway end-to-end service smoke: ผ่าน
- Takeaway import/reconciliation smoke: ผ่าน
- Frontend type-check: ผ่าน
- Frontend production build: ผ่าน (4,224 modules)
- Security boundary และ Android structural check: ผ่าน

ใช้ `scripts/run-wp23-takeaway-regression.sh` เพื่อรัน gate ซ้ำในเครื่องที่มี Docker และ Node

## ยังไม่ถือว่าผ่าน

- Android native Gradle/test เพราะเครื่องปัจจุบันไม่มี Java/Android SDK
- กล้อง, touch, Bluetooth printer, network interruption จริง, KDS/Pickup หลายเครื่อง
- approved Chambo snapshot และ production canary

สามกลุ่มนี้เป็น WP24–WP26 และต้องมีหลักฐานจากอุปกรณ์/ข้อมูล/ผู้อนุมัติจริง
