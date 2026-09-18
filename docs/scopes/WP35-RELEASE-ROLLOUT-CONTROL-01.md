# WP35 — Release, Rollout, Rollback and Owner Decision

วันที่: `2026-09-18`
สถานะ: **engineering_control_ready — current decision NO-GO pending external gates**

## Release rule

ใช้ `scripts/check-wp35-release-readiness.py` ตรวจ evidence JSON ก่อนทุก activation. ตัวตรวจเป็น fail-closed:
ถ้า approval, เวลา, approver หรือ SHA-256 ของหลักฐานแม้แต่รายการเดียวว่าง ผลต้องเป็น `blocked`.
ไฟล์ตัวอย่างอยู่ที่ `docs/production/wp35-release-evidence.example.json`

## Rollout waves

1. Platform Console + Company Admin หลัง operator MFA/handoff
2. Shared ERP หลัง accountant/tax review
3. Restaurant หนึ่งสาขาหลัง iPad/printer/payment/offline UAT
4. Retail หนึ่งสาขาหลัง selective migration และ scanner/printer/cash-drawer UAT
5. Central Kitchen ขอบเขตเล็กหลัง opening-lot/physical count; เปิด kitchen ก่อน distribution
6. Takeaway หนึ่งสาขาหลัง approved Chambo snapshot และ canary อย่างน้อย 60 นาที

แต่ละ wave ต้องระบุ activation owner, rollback owner, backup reference, start/end time,
monitoring route และ stop conditions. ห้ามเปิด wave ถัดไปพร้อมกันและห้าม big bang

## Stop and rollback conditions

- auth/tenant/permission isolation ผิดแม้หนึ่งรายการ
- duplicate sale/payment/order หรือ lost acknowledgement ที่ replay แล้วเกิดผลซ้ำ
- journal, payment, tax, stock, lot หรือ shared report reconciliation ไม่ตรง
- printer/payment/KDS/queue ทำให้ร้านดำเนินงานต่อไม่ได้
- error rate เกินเกณฑ์ที่ owner อนุมัติ หรือไม่มีผู้รับ alert
- operator/owner ขอหยุดไม่ว่าด้วยเหตุผลใด

Rollback ตาม wave: ปิด flag/routing ของส่วนนั้นก่อน, freeze writes, export/reconcile,
คืน route/image ที่ตรวจแล้ว และ restore เฉพาะเมื่อ additive rollback ไม่พอ. ห้ามลบฐานใหม่หรือ audit ledger

## Current evidence

- WP27–WP34 ฝั่ง engineering มีเอกสารและ automated evidence แล้ว
- fresh five-boundary backup อยู่ทั้ง server/Mac และ isolated restore ผ่าน
- Production ปัจจุบัน healthy; ยังไม่เปิด Retail dedicated routing หรือ Kitchen/Distribution writes
- release source/immutable manifest จะสร้างหลัง commit candidate และ deploy UAT จาก commit เดียวกัน

## External gates ที่ทำให้ decision ยังเป็น NO-GO

- Platform operator MFA/handoff
- accountant/tax review
- Restaurant และ Retail physical pilot
- Central Kitchen opening stock/stock-owner acceptance
- Takeaway approved snapshot, physical UAT และ one-branch canary
- residual defect acceptance และ final owner go/no-go

Engineering สามารถสร้าง UAT candidate และเตรียม runbook ต่อได้ แต่ห้ามเปลี่ยนรายการข้างต้นเป็น passed
หากไม่มีหลักฐานจากผู้รับผิดชอบจริง
