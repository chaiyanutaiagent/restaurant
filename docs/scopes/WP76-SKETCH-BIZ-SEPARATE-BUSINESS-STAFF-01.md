# WP76 — Sketch Biz Separate Business Staff

Date: 2026-09-27

Environment: UAT only (`restaurant-pos-uat-drill`)

Decision: **AUTOMATED STAFF ISOLATION PASS / HUMAN LOGIN UX DEFERRED / PRODUCTION HOLD**

## Final staff structure

Five Company shared-service users remain Company-wide because these functions
serve the shared ERP:

| Username | Name | Position |
|---|---|---|
| `test.owner` | ณัฐวุฒิ ศรีสุข | เจ้าของบริษัท |
| `test.accountant` | สุภาวดี มั่นคง | เจ้าหน้าที่บัญชี |
| `test.purchasing` | กิตติพงศ์ วงศ์ดี | เจ้าหน้าที่จัดซื้อ |
| `test.hr` | ชลธิชา พูนทรัพย์ | เจ้าหน้าที่ทรัพยากรบุคคล |
| `test.auditor` | รัชดา ธรรมรักษ์ | ผู้ตรวจสอบ |

### ครัวป่าปลาเขื่อน — KPP-01

`test.kpp.brand-manager`, `test.kpp.area-manager`,
`test.kpp.branch-manager`, `test.kpp.warehouse`, `test.kpp.service`,
`test.kpp.kitchen-manager`, `test.kpp.cashier`, `test.kpp.kitchen`

### The Loft Kitchen — TLK-01

`test.tlk.brand-manager`, `test.tlk.area-manager`,
`test.tlk.branch-manager`, `test.tlk.warehouse`, `test.tlk.service`,
`test.tlk.kitchen-manager`, `test.tlk.cashier`, `test.tlk.kitchen`

### The Loft Mini Mart — TLM-01

`test.tlm.brand-manager`, `test.tlm.area-manager`,
`test.tlm.branch-manager`, `test.tlm.warehouse`, `test.tlm.service`,
`test.tlm.cashier`

Retail intentionally has no Kitchen Manager or Kitchen Staff.

### Chambo — BKK-01 / Ozone One

`test.chambo.brand-manager`, `test.chambo.area-manager`,
`test.chambo.branch-manager`, `test.chambo.warehouse`,
`test.chambo.service`, `test.chambo.kitchen-manager`,
`test.chambo.cashier`, `test.chambo.kitchen`

Kitchen users are station-scoped and use `station_key=kitchen`; their access was
not widened to Branch scope.

## Automated evidence

- active test users: 35
- shared Company users: 5
- workspace-specific users: 30
- KPP / TLK / TLM / Chambo: 8 / 8 / 6 / 8
- active User/Branch links: 50
- active least-privilege scope assignments: 35
- canonical role coverage: 13/13
- previous broad operational users deactivated: 8
- the owner-supplied common UAT password verified for all 35 active users
- password is not stored in Git or this evidence document

Each workspace-specific user has exactly one active business context. The five
Company shared users retain all four contexts so Owner, Accounting, Purchasing,
HR and Audit can work across the shared ERP.

## Boundary

- All names are fictional UAT data.
- No Production user, role, password, branch, hostname or feature flag changed.
- Browser login repetition and human role-landing acceptance remain deferred.
