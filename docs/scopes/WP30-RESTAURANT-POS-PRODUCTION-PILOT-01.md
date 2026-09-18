# WP30 — Restaurant POS Production Pilot Readiness

วันที่: `2026-09-18`
สถานะ: **engineering_ready — physical pilot evidence pending**

## Automated evidence จาก release candidate

| Gate | ผล |
| --- | --- |
| Backend regression | `386` tests ผ่าน (`1` optional skip) |
| QR → kitchen → payment → ERP | ผ่านบน isolated stack |
| Stock/accounting/outbox handoff | payment `1`, recipe movements `3`, journal `1`, outbox `1` |
| Journal balance | debit/credit `169.00/169.00` |
| ERP reconciliation | sales และ payments ตรงกัน |
| Desktop/tablet browser suite | `26/26` ผ่าน |
| Offline/reconnect/idempotency load | `100` orders ผ่าน; sale/payment/session/outbox/journal อย่างละ `100`, recipe movement `300` |
| Frontend type-check/build | ผ่าน; `4,224` modules |
| Dependency audit | backend ไม่มี known vulnerability; frontend ไม่มี critical finding |
| Repository safety | ผ่านหลังแยก ignored local rollback backups ออกจาก Git-visible artifacts |

UAT server เดิมรัน release `582d6c7` และไม่ใช้เป็น final candidate evidence เพราะเก่ากว่า source ปัจจุบัน.
รอบทดลองกับ UAT เดิมหยุดเมื่อ recipe stock handoff ไม่ครบ; isolated current-source candidate ผ่าน flow เดียวกันครบ
จึงต้อง deploy candidate นี้ขึ้น UAT ก่อน physical pilot

## External pilot checklist

- [ ] iPad/Safari เปิดโต๊ะ สแกน QR ลูกค้าสั่งเอง KDS เสิร์ฟ เรียกบิล และชำระจริง
- [ ] ทดสอบเครื่องพิมพ์ใบเสร็จและครัว รวม retry/lost acknowledgement
- [ ] ทดสอบ PromptPay/เงินสด/คืนเงินตามนโยบายร้าน
- [ ] ตัดสต๊อกวัตถุดิบ สูตร และรายงานปิดกะตรงกับยอดนับจริง
- [ ] ทดสอบ offline/reconnect บนเครือข่ายร้านจริง
- [ ] ผู้จัดการร้านและ owner ลงชื่อเลือกหนึ่งสาขานำร่อง

## Decision

โค้ดพร้อมเป็น UAT release candidate แต่ยังไม่เปิด Restaurant pilot จริงหรือประกาศ production acceptance
จนกว่า checklist อุปกรณ์และผู้ปฏิบัติงานจะครบ
