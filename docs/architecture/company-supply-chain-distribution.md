# Company Supply Chain & Finished-Goods Distribution

สถานะ: WP6 local implementation / write dark launch

## Current-state audit

| ต้นทาง | สิ่งที่มีอยู่ | วิธีเชื่อม WP6 |
| --- | --- | --- |
| Restaurant POS | Central order/replenishment และ Transfer/Stock ใน Legacy ERP | ส่ง normalized demand พร้อม `source_module=restaurant_pos`, Brand, Branch, Product และ source document |
| Takeaway POS | Central order/production/transfer ใน Takeaway Database แยก | ส่ง demand ผ่าน API contract เท่านั้น; ห้าม query/transaction ข้ามฐาน |
| Retail POS | Product/Stock/Transfer ใน Legacy ERP แต่ยังไม่มี demand contract กลาง | ส่ง normalized demand พร้อม `source_module=retail_pos`; sale flow เดิมไม่ถูกเปลี่ยน |
| Central Kitchen | WP5 สร้าง Brand READY stock หลังผลิต | WP6 อ่าน/จอง/ตัดเฉพาะ `central_ready_location_id` ของ Brand |

## Ownership contract

| ข้อมูล | System of record | กติกา |
| --- | --- | --- |
| POS replenishment request | operational POS เจ้าของรายการ | WP6 เก็บ envelope/reference เท่านั้น ไม่ copy customer/receipt/payment |
| normalized Company demand | `CompanyDistributionDemand` | Company + source module + Brand + Branch + READY Product ต้องตรงกัน |
| shipment orchestration | `CompanyDistributionShipment` | ผูก Transfer Order เดิมหนึ่งใบ; ไม่เป็น stock balance ชุดใหม่ |
| stock reservation/movement | `TransferOrder`, `StockBalance`, `StockMovement` เดิม | เป็น authority เดียวของจอง, transfer out, transfer in และ reverse transfer |
| reject/return audit | `CompanyDistributionEvent` | append-only, idempotent; reject เป็น discrepancy ที่ไม่รับเข้าคลังขาย ส่วน return ใช้ reverse Transfer จริง |
| Company reconciliation | WP6 report | ส่ง = รับ + ปฏิเสธ + ระหว่างทาง; รับสุทธิ = รับ - คืน |

## Invariants

- Company มาจาก signed session เท่านั้น; client เลือก tenant/database ไม่ได้
- `restaurant_pos → restaurant`, `takeaway_pos → takeaway`, `retail_pos → retail_pos` ต้องตรงกับ `Brand.business_type`
- Branch ต้องเป็น active BrandBranch และมี `store_location_id`
- Product ต้องเป็น `central_ready` ของ Brand นั้น; READY location ต้องเป็นของ Company เดียวกัน
- การวางแผนใช้ Transfer flow เดิมตั้งแต่ draft → submit → approve เพื่อจอง stock ด้วย row lock
- เลข Transfer ใช้ลำดับรวมตามวันให้ตรงกับ global unique constraint; ป้องกันเลขชนระหว่าง Company
- การส่งใช้ `transfer_out`; การรับใช้ `transfer_in`; การคืนหลังรับสร้าง reverse Transfer และ movement คู่ใหม่
- ปฏิเสธก่อนรับไม่สร้าง stock ปลายทาง ยอดถูกแสดงแยกจาก lost/in-transit เพื่อให้ตรวจสอบได้
- demand/plan/dispatch/receive/reject/return/cancel มี idempotency fingerprint; key เดิม payload ต่างตอบ `409`
- branch role รับ `company.distribution.*` ไม่ได้; Company Owner ได้ view/manage
- ไม่มี customer PII ใน WP6 tables และไม่มี cross-database join

## Flow

```text
Restaurant / Takeaway / Retail source document
  -> normalized CompanyDistributionDemand
  -> validate Module + Brand + Branch + READY Product
  -> plan shipment
       -> existing TransferOrder draft/submit/approve (reserve READY)
  -> dispatch
       -> existing StockMovement transfer_out
  -> receive | reject
       -> existing StockMovement transfer_in | discrepancy audit
  -> optional return after receive
       -> reverse TransferOrder + transfer_out/transfer_in
  -> Company reconciliation by Module / Brand / Branch
```

## Migration, activation และ rollback

- migration `p14dist0016` สร้างตาราง demand/shipment/event ใหม่และไม่ backfill stock/order เดิม
- ค่าเริ่มต้น `COMPANY_DISTRIBUTION_WRITES_ENABLED=false`; read/report ใช้ตรวจข้อมูลได้ แต่ write ตอบ `409`
- flag ของ WP5 (`COMPANY_KITCHEN_WRITES_ENABLED`) เป็นอิสระและไม่ถูกเปิดโดย WP6
- ก่อนเปิดจริงต้อง backup, migration rehearsal, map READY/store locations, physical dispatch/receive UAT และ owner sign-off
- rollback: ปิด distribution flag, export/reconcile event + linked transfer manifest, ปล่อย POS/Transfer เดิมทำงานต่อ แล้ว downgrade เฉพาะเมื่อยังไม่มีข้อมูลจริงที่ต้องเก็บหรือมี restore ที่ตรวจแล้ว
