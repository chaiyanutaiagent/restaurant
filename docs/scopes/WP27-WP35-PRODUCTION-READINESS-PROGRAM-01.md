# WP27–WP35 — Foodchainservice Production Readiness Program

วันที่เริ่ม: `2026-09-18`
สถานะ: **in_progress — engineering gates เริ่มแล้ว; physical/owner evidence ห้ามสมมติ**
เป้าหมาย: ทำ Platform Console, Company Admin, Shared ERP, Restaurant POS, Retail POS,
Central Kitchen/Supply Chain และ Takeaway POS ให้พร้อมใช้งานจริงแบบ rollout ทีละขอบเขต

## หลักการตัดสิน

คำว่า `พร้อมใช้งานจริง` ต้องมีหลักฐานครบทุกข้อ:

1. business workflow และ permission/tenant boundary ผ่าน automated regression
2. migration, reconciliation และ rollback มีผลทดสอบกับสำเนาข้อมูลหรือ UAT
3. desktop และ tablet ผ่าน visual/interaction gate; hardware ที่เกี่ยวข้องผ่านบนอุปกรณ์จริง
4. monitoring, backup, restore และ incident owner พร้อม
5. ผู้ปฏิบัติงานและ owner ลงชื่ออนุมัติ; ห้ามใช้ผล automated แทน physical sign-off

Native mobile app และ Hotel PMS อยู่นอกโปรแกรมนี้ตามขอบเขตปัจจุบัน

## Work packages

| WP | ขอบเขต | Engineering exit | External exit | สถานะ |
| --- | --- | --- | --- | --- |
| WP27 | Baseline, gap matrix, UX handoff | inventory, automated baseline, runtime evidence | owner รับทราบขอบเขต | engineering complete |
| WP28 | Platform Console + Company Admin | auth/MFA, tenant lifecycle, module access, role/device/audit regression | operator handoff | engineering ready; MFA pending |
| WP29 | Shared ERP + Tax + reporting | inventory-to-accounting, tax period, cross-system reconciliation | accountant review | engineering ready; accountant pending |
| WP30 | Restaurant POS | table/QR/KDS/payment/receipt/stock/offline regression | iPad/printer/payment/operator UAT | engineering ready; physical pending |
| WP31 | Retail POS | dedicated DB parity/cutover, barcode/shift/payment/stock/offline regression | scanner/printer/cash-drawer UAT | engineering ready; cutover pending |
| WP32 | Central Kitchen + Distribution | opening-lot mapping, multi-brand stock, demand/production/distribution replay | stock owner sign-off | dark launch ready; writes off |
| WP33 | Takeaway/Chambo | Store/Central/Admin, signed import, reconciliation, rollback/canary tooling | approved snapshot + tablet/printer/operator UAT | engineering ready; canary pending |
| WP34 | Cross-system acceptance | security, load, five-boundary backup/restore, monitoring | defect acceptance | engineering ready; physical acceptance pending |
| WP35 | Release and rollout | immutable release, staged flags, runbooks, rollback rehearsal | final owner go/no-go | control ready; current NO-GO |

## Release waves

1. Platform Console และ Company Admin
2. Shared ERP โดยยังแยก tax/accountant sign-off
3. Restaurant หนึ่งสาขา
4. Retail หนึ่งสาขาหลัง dedicated-database cutover
5. Central Kitchen ด้วยรายการวัตถุดิบและแบรนด์จำกัด
6. Takeaway/Chambo หนึ่งสาขาแบบ canary
7. ขยายสาขาหลัง monitoring และ reconciliation ผ่าน

ห้ามทำ big-bang activation และห้ามเปิด Central Kitchen/Distribution write flags ก่อน WP32 exit

## UX/UI lane ที่ทำคู่ขนาน

Engineering ทำ data contract, workflow, security, tests และ operational shell ต่อได้โดยไม่รอ final visual.
นักออกแบบใช้ `docs/ux/FOODCHAINSERVICE-UX-UI-HANDOFF-WP27.md` เป็น source brief และส่งมอบเป็นรอบ:

- IA/navigation และ role journey
- desktop `1440×900` และ tablet landscape `1024×768`
- design tokens และ reusable component states
- critical-flow prototype
- usability findings และ implementation-ready specification

Frontend จะรับแบบผ่าน feature branch/flag และต้องรักษา API, permission, offline และ accessibility contract เดิม

## Evidence policy

- หลักฐาน automated เก็บจาก commit/release เดียวกับ candidate
- ห้ามใส่ password, token, `.env`, customer PII หรือ production database URL ในเอกสาร
- physical check ที่ยังไม่รันต้องเป็น `not_run` หรือ `blocked` เท่านั้น
- ทุก activation ต้องมี backup reference, rollback owner, monitoring window และ decision timestamp
