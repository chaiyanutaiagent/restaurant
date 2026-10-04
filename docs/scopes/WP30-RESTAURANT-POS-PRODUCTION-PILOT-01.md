# WP30 — Restaurant POS Production Pilot Readiness

วันที่: `2026-09-19`
สถานะ: **UAT_candidate_passed — physical pilot evidence pending**

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

## Live UAT candidate evidence

- Candidate commit: `dfb2441549950a865389010c8462757501655f53`
- Artifact SHA-256: `ae45437afbda5ab8a926128dc4b1b2d4dda216e38728a057f95fec45c672ee40`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/dfb2441549950a865389010c8462757501655f53`
- Pre-deploy UAT backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/wp35-before/restaurant-pos-prod-20260918T090908Z`
- Public `/`, `/pos`, `/admin`, `/health/ready`: HTTP `200`
- Migration heads: Legacy `p16taxops0018`, Platform `p13platform0017`, Restaurant `p6restaurant0007`,
  Retail `p8retail0002`, Takeaway `p6takeaway0008`
- Live API flow ผ่าน: payment `1`, recipe stock movement `3`, journal/outbox อย่างละ `1`,
  debit/credit `169.00/169.00`, Shared ERP reconciliation ตรงกัน
- Live public-domain browser flow ผ่าน `1/1` ใน `11.8s`: mobile QR, tablet KDS, serve, bill,
  payment, ERP report และหน้า POS/โต๊ะ/ออเดอร์/ลูกค้า/KDS ไม่มี horizontal overflow
- Browser report SHA-256: `357d4fd4a235f566e2b81ed853a67adcb0b1d337aa18a4a4a6f7100057e4dbf2`

รอบแรกบน UAT พบว่าตัวทดสอบสร้าง Brand ใหม่ แต่ UAT auto-login ใช้ Brand ของ workspace เดิม จึงไม่เกิด
recipe handoff. แก้ตัวทดสอบให้ยึด company/branch/brand จาก token ที่ server ออกจริงและเลือก Kitchen ticket
ด้วยชื่อโต๊ะเฉพาะ จากนั้น flow เดิมผ่านครบ. การแก้นี้ไม่ลดเงื่อนไขตรวจและไม่ถือเป็น physical-device evidence.

## External pilot checklist

- [ ] iPad/Safari เปิดโต๊ะ สแกน QR ลูกค้าสั่งเอง KDS เสิร์ฟ เรียกบิล และชำระจริง
- [ ] ทดสอบเครื่องพิมพ์ใบเสร็จและครัว รวม retry/lost acknowledgement
- [ ] ทดสอบ PromptPay/เงินสด/คืนเงินตามนโยบายร้าน
- [ ] ตัดสต๊อกวัตถุดิบ สูตร และรายงานปิดกะตรงกับยอดนับจริง
- [ ] ทดสอบ offline/reconnect บนเครือข่ายร้านจริง
- [ ] ผู้จัดการร้านและ owner ลงชื่อเลือกหนึ่งสาขานำร่อง

## Decision

Automated UAT candidate ผ่านแล้ว แต่ยังไม่เปิด Restaurant pilot จริงหรือประกาศ production acceptance
จนกว่า checklist อุปกรณ์และผู้ปฏิบัติงานจะครบ
