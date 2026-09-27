# WP25 — Takeaway Approved-data Dry Run

วันที่: 2026-09-17

สถานะ: **signed source dry-run completed — target apply ยังรอ human approval gate**

## ขั้นตอน

1. Data Owner freeze cutoff และสร้าง consistent snapshot ที่อ่านอย่างเดียว
2. ปิด/เคลียร์ open shift, order, production, transfer และ top-up หรือบันทึก blocker
3. ทำ mapping Company/Brand/Branch/Location และตรวจว่า target เป็น isolated database
4. สร้าง signed bundle ด้วย WP21 exporter และตรวจ offline ด้วย trusted public key
5. Preview ผ่านโดย blocker เป็นศูนย์ ก่อน import เข้า isolated target
6. รัน import ครั้งแรกและ replay ครั้งที่สอง; batch/จำนวน/ledger ต้องไม่เพิ่ม
7. เทียบ record count, historical sales, opening stock/reserved/value และ opening credit แบบ exact decimal
8. ยืนยัน history ไม่สร้าง payment, stock, notification หรือ ERP side effect
9. unresolved ต้องเป็น 0; หากไม่เป็น 0 ต้องมี owner waiver ต่อรายการ ไม่อนุญาต waiver รวมแบบไม่ระบุสาเหตุ
10. Data Owner และ Privacy Owner ลงนาม evidence

ใช้ template `docs/evidence/templates/wp25-approved-data-dry-run.json` และตรวจด้วย:

```bash
python3 scripts/validate-wp25-approved-dry-run.py <evidence.json>
```

## Exit gate

- trusted seal ผ่านและ manifest hash ถูก pin
- source/target control totals ตรงทุกค่า
- replay ปลอดภัย, historical side effects = 0
- unresolved = 0 หรือมี waiver ที่ตรวจได้
- approval ระบุผู้รับผิดชอบและเวลา

## ผลการรัน WP73

- อ่านฐาน Chambo จริงด้วย `READ ONLY` และ `REPEATABLE READ` สำเร็จ
- open shift/order/production/transfer/top-up/stock count เป็นศูนย์ทั้งหมด
- signed bundle ผ่าน hash, count, contract, security scan และ Ed25519 seal
- cutover preview: `ready=true`, blocker 0, 54 records from Ozone One only
- ยังไม่ execute target import, ไม่เปิด Takeaway transaction write และไม่เปลี่ยน Production
- ขั้น execute/replay/reconciliation และการรับรองผลสุดท้ายต้องรอ Data Owner,
  Privacy Owner และผู้ทดสอบจริงตาม Exit gate เดิม
