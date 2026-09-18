# WP27 — Production Readiness Baseline

วันที่: `2026-09-18`
Commit เริ่มต้น: `a0fdccf`
สถานะ: **engineering baseline passed — gap matrix และ UX handoff พร้อม; external gates ยังเปิดอยู่**

## Automated baseline

| Gate | ผล |
| --- | --- |
| Backend full regression | `386` tests ผ่าน |
| Frontend TypeScript | ผ่าน |
| Frontend production build | ผ่าน, `4,224` modules |
| Production backend | healthy, image `restaurant-pos-backend:auth-a0fdccf` |
| Production frontend | running, image `restaurant-pos-frontend:ui-e4200ca` |
| Production ingress | nginx และ Cloudflare tunnel running |
| Production disk | ใช้ `19%` ของ volume |

Backend regression ต้องรับค่าจาก `.env.example`; การรัน image โดยไม่ส่ง environment ล้มจาก config validation
และไม่นับเป็น application defect. การรันซ้ำด้วย environment contract ที่ถูกต้องผ่านทั้งหมด

## Production database baseline

| Boundary | Runtime head | Runtime routing |
| --- | --- | --- |
| Legacy | `p16taxops0018` | Restaurant และ Retail ยังใช้ Legacy |
| Platform Core | `p13platform0017` | Identity, tenant, module access, shared reporting |
| Restaurant | `p6restaurant0007` | standby/transition boundary |
| Retail | `p8retail0002` | schema พร้อม แต่ Production traffic ยังไม่ cut over |
| Takeaway | `p6takeaway0008` | dedicated runtime เปิดอยู่ |

Reference projector และ Shared Reporting projector เปิดอยู่. Retail reference projector ยังปิดตาม Legacy routing.
Takeaway runtime เปิด แต่ยังไม่ถือว่าผ่าน canary/cutover gate

## Module gap matrix

| ส่วน | สิ่งที่มีแล้ว | Gap ที่ต้องปิดในโปรแกรมนี้ |
| --- | --- | --- |
| Platform Console | owner auth, MFA, tenant lifecycle, billing/support/audit/operations | operator handoff, session/security review, alert ownership |
| Company Admin | company/branch/user/role/device/module workspace | end-to-end role/device acceptance และ onboarding usability |
| Shared ERP | catalog, stock, purchase, payable, accounting, HR, CRM, tax/e-Tax, logistics, reports | representative reconciliation, accountant review, external/legal boundary |
| Restaurant POS | table, session QR, customer order, KDS, pickup, payment, receipt, recipes, stock/offline | physical iPad/printer/payment/operator evidence |
| Retail POS | sale, barcode, shift, payment, receipt, stock/report | dedicated DB cutover, scanner/printer/cash-drawer/offline evidence |
| Central Kitchen | canonical ingredient, lot, production, demand/report | opening-lot mapping; write flags ยังปิด; stock-owner sign-off |
| Distribution | normalized demand, shipment, receipt/reconciliation | write flag ยังปิด; staged replay/rollback evidence |
| Takeaway POS | Store/Central/Admin, paid-first, queue/KDS/pickup, stock/production/credit/report/import tooling | approved source snapshot, physical UAT, one-branch canary และ owner go |

## Recovery baseline

มี five-boundary backup หลัง unified cutover วันที่ `2026-09-17` ที่ server และเคยมี isolated restore drill
ใน WP15. WP34/WP35 ต้องสร้าง backup ใหม่จาก release candidate และทำ restore/rollback evidence ใหม่;
ห้ามใช้ผลเก่าแทน final release evidence

## WP27 exit

- [x] ระบุ 7 production areas และ runtime ownership
- [x] รัน backend/frontend automated baseline
- [x] ตรวจ Production health, images, migration heads, disk และ backup inventory แบบ read-only
- [x] ระบุ external gates โดยไม่ปลอมผล
- [x] จัดทำ UX/UI handoff สำหรับ designer lane
- [x] กำหนด WP28–WP35 และ release waves

งานถัดไป: WP28 Platform Console และ Company Admin readiness
