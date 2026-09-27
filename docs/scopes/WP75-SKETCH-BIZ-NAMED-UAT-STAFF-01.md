# WP75 — Sketch Biz Named UAT Staff

Date: 2026-09-27

Environment: UAT only (`restaurant-pos-uat-drill`)

Decision: **AUTOMATED IDENTITY GATE PASS / HUMAN LOGIN UX DEFERRED / PRODUCTION HOLD**

## Result

One named fictional test user was created for every canonical role preset in
`บริษัท สเก็ตช์ บีซ จำกัด`:

| Username | Name | Position | Canonical role | Scope |
|---|---|---|---|---|
| `test.owner` | ณัฐวุฒิ ศรีสุข | เจ้าของบริษัท | Company Owner | Company |
| `test.brand-manager` | พิมพ์ชนก วัฒนกิจ | ผู้จัดการแบรนด์ | Brand Manager | 4 brands |
| `test.branch-manager` | ธนภัทร เจริญผล | ผู้จัดการสาขา | Branch Manager | 4 branches |
| `test.accountant` | สุภาวดี มั่นคง | เจ้าหน้าที่บัญชี | Accountant | Company |
| `test.purchasing` | กิตติพงศ์ วงศ์ดี | เจ้าหน้าที่จัดซื้อ | Purchasing | Company |
| `test.warehouse` | อนุชา ใจมั่น | เจ้าหน้าที่คลังสินค้า | Warehouse | 4 branches |
| `test.hr` | ชลธิชา พูนทรัพย์ | เจ้าหน้าที่ทรัพยากรบุคคล | HR | Company |
| `test.auditor` | รัชดา ธรรมรักษ์ | ผู้ตรวจสอบ | Auditor | Company |
| `test.area-manager` | วรเมธ ตั้งใจ | ผู้จัดการเขต | Area Manager | 4 brands |
| `test.service-staff` | กัญญารัตน์ ยิ้มแย้ม | พนักงานบริการ | Service Staff | 4 branches |
| `test.kitchen-manager` | สมชาย รสเลิศ | ผู้จัดการครัว | Kitchen Manager | 4 branches |
| `test.cashier` | ปวีณา เงินดี | พนักงานขายและแคชเชียร์ | Cashier | 4 branches |
| `test.kitchen-staff` | เอกชัย ครัวดี | พนักงานครัว | Kitchen Staff | 3 kitchen stations |

All users have the four intended product contexts: KPP-01, TLK-01, TLM-01 and
BKK-01. KPP-01 is the default context. The station-scoped Kitchen Staff login
must use `station_key=kitchen`; it is intentionally not widened to Branch scope.

## Automated verification

- active named test users: 13
- canonical role coverage: 13/13
- active User/Branch context links: 52
- active least-privilege scope assignments: 36
- supplied UAT password verified against all 13 hashes during preparation
- password was passed only through a one-shot environment variable and is not
  stored in Git or this evidence document
- every change has an immutable AuditLog record and a Platform projection event

## Boundary

- These are fictional UAT identities, not real employees.
- UAT login bypass remains an environment decision and was not changed here.
- No Production identity, password, role, branch or flag was changed.
- Repeated browser login testing and human role-landing acceptance remain
  deferred as requested.
