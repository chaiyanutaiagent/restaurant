# UI Showcase Dataset 01

## Purpose

ชุดข้อมูลจำลองนี้ใช้เติมหน้า UAT ให้มีข้อมูลครบพอสำหรับตรวจและจัด UI ของ Foodchainservice โดยไม่เปิดใช้ Production และไม่คัดลอกข้อมูลส่วนบุคคลจริง

## Safety boundary

- รันได้เฉพาะ `development` ที่ public URL ขึ้นต้นด้วย `https://uat-`
- ต้องใช้ Platform identity, Restaurant บน Legacy, Retail DB และ Takeaway DB ตาม topology ของ UAT
- ต้องระบุ `--yes`, Company UUID และชื่อผู้ดูแลระบบทุกครั้ง
- ใช้ UUID แบบ deterministic และ upsert ข้อมูลเดิม จึงรันซ้ำได้โดยไม่เพิ่มรายการซ้ำ
- อีเมลและ webhook ใช้โดเมน `example.invalid`; API key เก็บเฉพาะ hash ที่ใช้เข้าสู่ระบบไม่ได้
- ไม่แก้ Production และไม่เปิด feature เพิ่มใน Production

## Coverage

| พื้นที่ | ข้อมูลที่สร้างเพื่อทดสอบ UI |
|---|---|
| Platform / SaaS | แพ็กเกจ, ใบแจ้งหนี้หลายสถานะ, billing events, support tickets, privacy requests, อุปกรณ์, usage/operations snapshots |
| Restaurant POS | เมนูและหมวด, 4 โต๊ะที่มี session, QR/staff orders, KDS สถานะรอ–กำลังทำ–พร้อม–เสร็จ, ยอดขาย/ชำระเงิน/คืนเงิน/ยกเลิก |
| Retail POS | 4 หมวด, 16 สินค้าและบริการ, barcode, price list, สต๊อกปกติ/ต่ำ/หมด/จอง, ยอดขายหลายช่องทางชำระ |
| Takeaway POS | 4 หมวด, 16 เมนู, branch catalog, สต๊อก, กะ, ออเดอร์ทุกสถานะ, KDS, ใบเสร็จ, pickup token, สั่งส่วนกลาง, ผลิต, โอน, เครดิตสาขา |
| จัดซื้อ | ผู้จำหน่าย 3 ราย, PO ร่าง/อนุมัติ/รับบางส่วน/รับครบ/ยกเลิก และ GR |
| คลัง | หลาย location, stock balances, โอนระหว่างสาขาหลายสถานะ, ตรวจนับร่าง/กำลังนับ/เสร็จพร้อมผลตรง–เกิน–ขาด |
| CRM | tier, tag, ลูกค้า 8 รูปแบบ, คะแนนสะสม/แลก, active/inactive/เฝ้าระวัง |
| บุคลากร | 5 แผนกและตำแหน่ง, พนักงาน 6 คน, เงินเดือน, เวลาเข้างานปกติ/สาย/ขาด/OT, ลาหลายสถานะ, payroll |
| บัญชีและภาษี | ผังบัญชีและ journal ที่สมดุล; ใช้ข้อมูลภาษี UAT เดิมที่เตรียมไว้แล้ว |
| ขนส่ง | งาน pending/ready/shipped/delivered/returned พร้อม item และ timeline |
| Integration | API keys active/expiring/revoked, webhook สำเร็จ/ล้มเหลว/รอลองใหม่, external orders หลายสถานะ |
| ครัวกลาง | ครัว, วัตถุดิบ canonical, lots, movement และ demand จาก Restaurant/Takeaway/Retail |

## Command

```bash
python -m app.cli.seed_ui_showcase \
  --company-id <uat-company-uuid> \
  --username admin \
  --yes
```

ก่อนรันบน UAT ต้องสำรองฐานข้อมูลทั้ง Platform, Legacy, Restaurant, Retail และ Takeaway หลังรันให้ตรวจจำนวนข้อมูลและเปิดหน้า UI หลักทุกหมวด ส่วนการลบชุดข้อมูลให้ restore จาก backup ก่อน seed ซึ่งเป็นวิธี rollback ที่คงความสัมพันธ์ของข้อมูลได้แน่นอนที่สุด

## UAT execution evidence

- วันที่รัน: 2026-09-16
- UAT URL: `https://uat-pos.foodchainservice.com`
- Backend image: `restaurant-pos-backend:ui-showcase-a81d0d9`
- Pre-seed rollback backup: `/home/behappyaiagent/restaurant-uat-backups/ui-showcase-pre-20260916T102915Z`
- สร้าง dump ครบ 5 ฐาน: Legacy, Platform Core, Restaurant, Retail และ Takeaway พร้อม SHA-256
- รันคำสั่ง seed สำเร็จ 2 รอบติดต่อกันเพื่อยืนยัน idempotency
- ตรวจ HTTPS `/health`, `/pos` และ `/admin` ได้ HTTP 200
- Production backend คงเดิมที่ `restaurant-pos-backend:4c1c2ba` และมีสถานะ healthy

จำนวนหลักที่ตรวจจากฐานข้อมูลหลังรัน: Platform invoice 3, support ticket 3, device 4; Legacy sale 7, PO 5, customer 8, employee 6, shipment 5, production order 3 และ distribution demand 3; Retail product 16 และ sale 7; Takeaway catalog 16, order 7, central order 3 และ production batch 3
