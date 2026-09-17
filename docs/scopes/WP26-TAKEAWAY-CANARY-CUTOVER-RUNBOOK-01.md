# WP26 — Takeaway Canary / Cutover Runbook

วันที่: 2026-09-17

สถานะ: **ready_to_run — blocked ด้วย WP24, WP25, final backup, canary และ owner go/no-go**

## Hard gates

- WP24 physical UAT evidence ผ่านและ pin SHA-256
- WP25 approved-data dry run ผ่านและ pin SHA-256
- release commit/artifact/signature ตรงกับ UAT candidate
- final backup อยู่ทั้ง server และ Mac, มี SHA-256 และทำ restore verification
- maintenance/rollback owner, operator, monitoring dashboard และ communication channel พร้อม

## Canary หนึ่งสาขา

1. Freeze source writes ตามเวลาที่อนุมัติและสร้าง final delta/snapshot
2. ตรวจ open operation เป็นศูนย์และรัน cutover preview ใหม่
3. Execute ด้วย owner approval, backup และ rollback reference เดิมที่ pin ไว้
4. เปิดเฉพาะสาขา canary; ระบบอื่น/สาขาอื่นไม่ถูกเปลี่ยน route
5. ทดสอบ sale, QR, payment, receipt, KDS, Pickup, shift, stock, central order และ ERP
6. เฝ้าดูอย่างน้อย 60 นาที: error ≤ 1%, duplicate/stock/payment mismatch = 0
7. รัน rollback drill ตาม reference และบันทึก recovery time ก่อนตัดสินใจจริง
8. Owner ลง `go` หรือ `no-go`; production activation ทำได้เมื่อทุก hard gate ผ่านเท่านั้น

ใช้ template `docs/evidence/templates/wp26-canary-cutover.json` และตรวจด้วย:

```bash
python3 scripts/check-wp26-canary-readiness.py <evidence.json>
```

ตัวตรวจนี้อ่านหลักฐานอย่างเดียวและ **ไม่มีคำสั่งเปิด Production** เพื่อป้องกันการ activate จาก checklist ที่ยังไม่ครบ

## Rollback triggers

- duplicate order/payment ใด ๆ
- stock/credit/reconciliation mismatch ใด ๆ
- tenant/permission leak หรือ signed context ไม่ตรง
- error rate เกิน 1% ในหน้าขาย/ชำระ/KDS/Pickup
- printer/offline failure ที่ทำให้ operator ขายต่อหรือยืนยันยอดไม่ได้

เมื่อ trigger เกิด: หยุด traffic canary, เก็บ log/evidence, ทำ rollback ตาม reference, ตรวจ restore และประกาศ no-go

## สถานะปัจจุบัน

ยังไม่ได้สร้าง final backup, ยังไม่ได้เปิด canary และยังไม่มี owner go/no-go ดังนั้น Production ยังไม่ถูก activate
