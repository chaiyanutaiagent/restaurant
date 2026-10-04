# WP24 — Takeaway Physical UAT Runbook

วันที่: 2026-09-17

สถานะ: **ready_to_run — blocked ด้วยอุปกรณ์จริงและผู้ทดสอบ**

## เป้าหมาย

พิสูจน์ UAT candidate เดียวกันบน Android app และ iPad Safari โดยเก็บภาพ/วิดีโอ/log ต่อ check
ห้ามใช้ผลจาก desktop browser แทน camera, touch, Bluetooth printer หรือ network interruption จริง

## ลำดับทดสอบ

1. บันทึก Git commit, package ID, version และ SHA-256 ของ signed UAT APK
2. ติดตั้ง `com.foodchainservice.takeaway.uat` บน Android และเปิด workspace ที่ถูกต้อง
3. เปิด UAT URL บน iPad Safari ตรวจ touch target, scroll, keyboard และ responsive layout
4. ทดสอบกล้องสแกน QR ทั้ง POS และ customer QR
5. Pair Bluetooth printer, deny/allow permission, พิมพ์ customer/merchant copy และตัดกระดาษ
6. ปิด printer/กระดาษหมด/เปิดใหม่ แล้ว reconnect โดยไม่สร้างบิลซ้ำ
7. ตัดเครือข่ายระหว่างขายและหลัง server รับรายการ (lost ACK), ต่อใหม่แล้วตรวจ replay
8. ใช้ KDS อย่างน้อยสองเครื่องพร้อมกัน ตรวจสถานะและ duplicate action
9. ตรวจ Pickup/public status ตั้งแต่ queued ถึง picked up
10. เปิด/ปิดกะ, stock, central order, production/transfer flow ตามสิทธิ์
11. ส่งมอบให้ operator อีกคนทำซ้ำตามคู่มือโดยผู้พัฒนาไม่ชี้นำ

เริ่มจากสำเนา `docs/evidence/templates/wp24-physical-uat.json` แล้วแนบ evidence reference ทุกข้อ
ก่อนอนุมัติให้รัน:

```bash
python3 scripts/validate-wp24-physical-uat.py <evidence.json>
```

ตัวตรวจจะ fail หากมีข้อ `not_run`, ไม่มีหลักฐาน, ขาด Android/iPad หรือยังไม่มี owner approval

## Exit gate

- checks ทั้ง 11 ข้อเป็น `passed`
- ไม่มี blocker ระดับหยุดขาย/ยอดเงิน/stock/tenant/security
- operator และ owner ระบุชื่อกับเวลาอนุมัติ
- defect ที่ยอมรับได้ต้องมี ticket/owner waiver ชัดเจน ห้ามแก้สถานะใน evidence เฉย ๆ
