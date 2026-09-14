# Company Shared Central Kitchen Ownership

สถานะ: WP5 local implementation / write dark launch

## ขอบเขตที่ตรวจพบก่อนทำ WP5

ระบบเดิมมี `Brand.central_branch_id`, `central_location_id`, `central_ready_location_id`,
Brand recipe, `StockBalance`/`StockMovement`, replenishment และ transfer อยู่ในฐาน Legacy ERP แล้ว
แต่ identity ของวัตถุดิบและ production flow ยังผูกกับแต่ละ Brand จึงไม่ควรรวมยอดเดิมด้วยชื่อหรือ SKU
แบบคาดเดา

WP5 จึงเพิ่มชั้น Company Central Kitchen ในฐาน Legacy ERP เดิมก่อน ไม่ย้าย Restaurant, Takeaway,
Retail หรือ Hotel database และไม่แก้ primary key ของข้อมูลเดิม

## Ownership contract

| ข้อมูล | System of record | กติกา |
| --- | --- | --- |
| ครัวกลางและ RAW location | `CompanyKitchen` | หนึ่ง active kitchen ต่อ Company; location ต้องอยู่ Company/branch เดียวกัน |
| วัตถุดิบจริง | `CompanyIngredient` | canonical Product ต้องเป็น Company-level `central_raw` และไม่ผูก Brand |
| SKU/วัตถุดิบในสูตรแบรนด์ | `CompanyIngredientAlias` | Brand Product หนึ่งตัว map canonical ingredient ได้หนึ่งตัว พร้อม conversion ชัดเจน |
| RAW lot และคงเหลือ | `CompanyIngredientLot` | เป็น authority ของ shared flow; ห้ามรวมกับ Brand stock เดิมอัตโนมัติ |
| RAW audit ledger | `CompanyKitchenMovement` | append-only; มี Company, kitchen, location, ingredient, lot, source และ Brand เมื่อเกิดจาก production |
| Demand | `CompanyProductionDemand` | แยก Brand, Branch, output product, needed date และ source document |
| Production order/input | `CompanyProductionOrder` / `CompanyProductionInput` | รวมคิววางแผนได้ แต่ recipe, output, READY location, cost และผลผลิตยังเป็นของ Brand |
| Finished goods | `StockBalance` / `StockMovement` เดิม | รับเข้าคลัง READY ของ Brand ผ่าน Stock service เดิม |
| Transfer ไปสาขา | Transfer/Stock ledger เดิม | WP5 ไม่สร้าง transfer ซ้ำ; ใช้ finished-goods identity และ location เดิม |

## Invariants

- ทุก query/write ใช้ `company_id` จาก signed session; request เลือก Company หรือ database ไม่ได้
- Company Admin ใช้ `company.kitchen.view/manage`; branch role รับ permission นี้ไม่ได้
- หน่วยรองรับแบบระบุชัด: mass (`mg`, `g`, `kg`), volume (`ml`, `l`) และ count (`ea`, `ชิ้น`)
- conversion ข้ามมิติถูกปฏิเสธ และทุกยอดใน shared ledger ถูกเก็บเป็น base unit
- costing ใช้ FIFO ตามวันหมดอายุ/วันรับเข้า; negative stock เป็น `false` เท่านั้นใน WP5
- issue ล็อก transaction และ lot row; concurrent completion ตัดได้ไม่เกินยอดจริง
- receipt, demand, order, completion และ reversal มี idempotency key; replay ไม่สร้าง movement ซ้ำ
- reversal คืน RAW เข้า lot เดิมและหัก finished goods ได้ต่อเมื่อ READY balance ยังพอ
- รายงานใช้ business date ตาม timezone ของครัวกลาง ค่าเริ่มต้น `Asia/Bangkok`

## Flow

```text
Brand/Branch demand
  -> Brand production order + Brand recipe
  -> Brand ingredient aliases
  -> FIFO issue จาก Company RAW lots
  -> receive finished goods เข้า Brand READY stock
  -> transfer ไปสาขาด้วย transfer flow เดิม
  -> รายงาน Company รวมภาพ แต่ group ตาม Brand
```

ตัวอย่าง “หมูแดดเดียว” และ “หมูหนักย่าง” map วัตถุดิบสูตรของตนเข้าหมู canonical ตัวเดียว
จึงตัด RAW lots กองเดียวกัน แต่ output Product, READY balance, production cost และ report row ไม่ปะปนกัน

## Migration และ rollout

- migration `p13kitchen0015` สร้างเฉพาะตารางใหม่และไม่ backfill/รวม stock เดิม
- migration ต้องรันหลัง backup และ reconciliation manifest; downgrade กลับ `p12route0014` ได้เมื่อ write path ปิด
- ค่าเริ่มต้น `COMPANY_KITCHEN_WRITES_ENABLED=false`; API read/report ใช้ตรวจ setup ได้ แต่ write endpoint ตอบ `409`
- เปิดจริงได้หลัง owner map canonical ingredient/alias, กำหนด opening lots ที่ตรวจนับจริง, ทดสอบบน UAT
  และลงนาม rollback checklist

## Rollback

1. ปิด `COMPANY_KITCHEN_WRITES_ENABLED` ก่อน เพื่อหยุด receipt/production/reversal ใหม่
2. export order, input, lot และ movement manifest แล้ว reconcile RAW/READY balances
3. ให้ Restaurant/Takeaway/Retail ใช้ operational flow เดิมต่อได้โดยไม่พึ่ง WP5
4. ถ้ายังไม่เคยเปิด write หรือจัดการ ledger แล้ว จึง downgrade `p13kitchen0015` ไป `p12route0014`
5. ห้ามลบ shared ledger เพื่อแก้ยอด; ใช้ reversal และเก็บ source identity เสมอ
