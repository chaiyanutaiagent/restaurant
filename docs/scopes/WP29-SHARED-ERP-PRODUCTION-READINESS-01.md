# WP29 — Shared ERP, Tax and Reporting Production Readiness

วันที่: `2026-09-18`
สถานะ: **engineering_ready — accountant review and legal/provider boundary pending**

## ขอบเขตที่ยืนยันแล้ว

- สินค้า หน่วยนับ คลัง สต๊อก การโอน และต้นทุน
- จัดซื้อ รับสินค้า เจ้าหนี้ การจ่าย และหัก ณ ที่จ่าย
- ผังบัญชี journal, trial balance และ profit/loss
- Tax Profile ระดับ Company/Branch และอัตราภาษีตามช่วงเวลา
- ทะเบียนภาษีขาย/ซื้อ การกระทบ e-Tax งวดภาษี และ export ที่ตรวจ hash ได้
- Shared Reporting แยก Restaurant, Retail และ Takeaway ตาม Company/Brand/Branch
- permission ของ Company Owner, Accountant และ Purchasing แยกตามหน้าที่

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | รวมใน WP27: `386` tests ผ่าน |
| ERP/tax/reporting focused regression | `50/50` ผ่าน |
| Production journal balance | ไม่พบรายการเสียสมดุล |
| Production stock invariant | ไม่พบ on-hand/reserved ติดลบหรือ reserved เกิน on-hand |
| Production accounts payable invariant | ไม่พบยอดติดลบหรือ total/paid/remaining ไม่ตรง |
| Shared Reporting source health | `legacy_pos`, `restaurant_pos`, `takeaway_pos` เป็น `healthy`; failure `0` |
| Production business data | ยังไม่มี journal/stock/AP/tax/reporting fact จริง จึงไม่มีรายการค้างกระทบยอด |

การตรวจ Production รอบนี้เป็น read-only และไม่สร้างหรือแก้ข้อมูลธุรกิจ

## UAT evidence ที่คงอยู่

UAT ภาษีเคยผ่านวงจร Restaurant/Retail/Takeaway output VAT, Purchasing input VAT,
Supplier Invoice/AP/WHT, e-Tax PDF/XML, Review/Close/Reopen, export 7 ประเภท และ SHA-256.
หลังการแก้ regression รอบล่าสุดมี blocker `0`, warning `0`, pending `0` ตาม
`WP9-TAX-OPERATIONS-02` โดยใช้ข้อมูลจำลองเท่านั้น

## External hard gates

- [ ] นักบัญชีตรวจ Tax Profile, mapping บัญชี, ภาษีซื้อ/ขาย และแบบส่งออกด้วยข้อมูลจำลอง
- [ ] เจ้าของกิจการยืนยันนโยบาย VAT รวม/แยก, รหัสสาขาภาษี และ consolidated filing (ถ้ามี)
- [ ] ระบุผู้รับผิดชอบปิดงวด เปิดงวดใหม่ และอนุมัติ manual journal
- [ ] เลือก e-Tax Service Provider และ digital certificate ก่อนเชื่อมส่งจริง
- [ ] ทดสอบหนึ่งงวดจำลองโดยผู้ใช้บทบาท Accountant/Purchasing บนอุปกรณ์จริง

## Decision

Shared ERP พร้อมให้ทำ release candidate และเริ่มข้อมูล master จริงแบบควบคุมได้ แต่ยังห้ามถือว่า
“ยื่นภาษีจริงพร้อม” จน accountant/legal/provider gates ด้านบนได้รับการอนุมัติและแนบหลักฐานใน WP35
