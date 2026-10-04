# P6-TAKEAWAY-BOUNDARY-DRAFT-03 — Database, Permission และ ERP Contract

วันที่จัดทำ: 2026-09-11

สถานะ: **implemented_dark_launch — feature ปกติปิดและยังไม่ deploy**

Owner อนุมัติเมื่อ 11 กันยายน 2026 ให้ implement ระหว่างพัก physical UAT ได้เฉพาะแบบ
dark launch การเปิด feature, UAT/Production deployment, real Chambo import และ cutover
ยังต้องผ่าน Restaurant Completion Gate และอนุมัติแยกต่างหาก

เอกสารที่เกี่ยวข้อง:

- `P6-TAKEAWAY-DISCOVERY-01.md`
- `P6-TAKEAWAY-CAPABILITY-MATRIX-02.md`
- `P6-CHAMBO-DATA-CONTRACT-04.md`
- `P6-CHAMBO-DRY-RUN-05.md`
- `P6-TAKEAWAY-IMPLEMENTATION-06.md`
- `P1-DATABASE-BOUNDARY-03.md`
- `P4-SALE-HANDOFF-03.md`

## Architecture Decisions

1. Takeaway operational data มี system of record อยู่ใน Takeaway Database เท่านั้น
2. Company/Brand/Branch/Staff/Device/Entitlement มี system of record อยู่ใน Control Plane
3. Takeaway เก็บ local reference projection และ immutable snapshots แต่ไม่มี cross-database FK
4. ERP/accounting/reporting รับ versioned outbox events ห้าม query Takeaway tables โดยตรง
5. Restaurant รับกลับยังอยู่ใน Restaurant Database และไม่ถูกย้ายเข้า Takeaway
6. Chambo เป็น migration source/reference ไม่ใช่ runtime dependency ของ Foodchainservice
7. เปิด Takeaway session factory ได้ต่อเมื่อ URL, migration head, readiness และ feature flag พร้อม

## Runtime Boundary

### Configuration

ค่าที่ implement แล้ว:

```text
TAKEAWAY_DATABASE_URL=<required explicit URL>
TAKEAWAY_SERVICE_DATABASE=disabled|takeaway
REFERENCE_PROJECTOR_ENABLED=false|true
TAKEAWAY_FEATURE_ENABLED=false|true
```

ข้อกำหนด:

- staging/production ห้าม fallback `TAKEAWAY_DATABASE_URL` ไป `DATABASE_URL` หรือ
  `RESTAURANT_DATABASE_URL`
- `TAKEAWAY_FEATURE_ENABLED=true` ต้องใช้ `IDENTITY_DATABASE=platform_core`, reference
  projector, distinct database name และ migration head ที่รองรับ release เดียวกัน
- readiness ต้อง fail closed หากเปิด feature แต่ Takeaway database/projector ไม่พร้อม
- การปิด feature ต้องปิด route/entitlement ใหม่ แต่ไม่ทำลาย pending outbox หรือข้อมูลเดิม

### Session Registry

```text
TARGET_DATABASE_SESSION_FACTORIES
  platform_core -> PlatformSessionLocal
  restaurant    -> RestaurantSessionLocal
  retail_pos    -> legacy adapter ระหว่าง transition
  takeaway      -> TakeawaySessionLocal เมื่อ feature พร้อมเท่านั้น
```

`operational_session_factory_for()` ต้องเลือกจาก server-owned business context เท่านั้น
ห้ามรับชื่อฐานข้อมูลหรือ URL จาก request/header/client

### Migration และ Recovery

- Alembic environment/head ของ Takeaway แยกจาก legacy, Platform และ Restaurant
- migration เป็น additive-first และทดสอบ upgrade → downgrade → upgrade ใน isolated database
- backup แยก `takeaway.dump`, uploads และ manifest/checksum
- restore drill กู้ไปชื่อ database ใหม่และตรวจ schema head, row counts และ invariants
- production restore/cutover ต้องมี owner, RPO, downtime, source release และ rollback release

## Reference Projection

Takeaway Database เก็บ projection เพื่อ validate context ภายใน transaction โดยไม่ join
Control Plane ข้าม database:

| Projection | ฟิลด์หลัก | หมายเหตุ |
| --- | --- | --- |
| `takeaway_company_refs` | company_id, status, credential_version, source_version | ไม่มี billing secret |
| `takeaway_brand_refs` | company_id, brand_id, slug, name, status, source_version | ต้องเป็น `business_type=takeaway` |
| `takeaway_branch_refs` | company_id, brand_id, branch_id, code, name, status, source_version | branch ต้องสืบทอด Takeaway |
| `takeaway_staff_assignment_refs` | company_id, brand_id, branch_id, user_id, role_key, status, source_version | permission resolution จาก Control Plane contract |
| `takeaway_device_refs` | company_id, brand_id, branch_id, device_id, type, station_key, credential_version, revoked_at | credential จริงยังอยู่ Control Plane |

ทุก projector message ต้องมี event ID/version, processed inbox record และ idempotent upsert
หาก projection ล้าหลังหรือ context ไม่ตรงให้ปฏิเสธ operation ที่เปลี่ยนข้อมูล

## Operational Schema Draft

ทุกตาราง operational ต้องมี UUID primary key, `company_id` และขอบเขต Brand/Branch ตามชนิด
ข้อมูล รวมทั้ง timestamps และ audit actor/source document ที่เหมาะสม

### Catalog และ Recipe

| ตารางเสนอ | หน้าที่ | Invariant สำคัญ |
| --- | --- | --- |
| `takeaway_menu_categories` | หมวดเมนูต่อแบรนด์ | code ไม่ซ้ำใน company+brand |
| `takeaway_menu_items` | เมนูขาย ราคา ภาษี สถานะ | SKU/code ไม่ซ้ำใน company+brand |
| `takeaway_menu_versions` | snapshot เมนูที่เผยแพร่ | published version แก้ย้อนหลังไม่ได้ |
| `takeaway_stock_items` | วัตถุดิบ/สินค้าสำเร็จ/UOM | item identity ระดับ company; brand visibility แยก table |
| `takeaway_item_brand_links` | ให้หลายแบรนด์ใช้ stock item เดียว | company ของ item/brand ต้องตรงกัน |
| `takeaway_recipe_versions` | สูตรขาย/สูตรผลิต versioned | active range ห้ามซ้อนกันต่อ output item |
| `takeaway_recipe_ingredients` | input qty/UOM/loss | reject loop และ conversion ที่ไม่สมบูรณ์ |

### Store Sale, Queue และ Fulfilment

| ตารางเสนอ | หน้าที่ | Invariant สำคัญ |
| --- | --- | --- |
| `takeaway_orders` | paid-first/customer QR order | unique company+branch+client_order_id |
| `takeaway_order_items` | price/tax/recipe snapshot | totals คำนวณจาก immutable snapshot |
| `takeaway_payments` | payment reference/tender/change | unique provider/idempotency reference |
| `takeaway_receipt_documents` | receipt number/render snapshot | running number unique ต่อ company/branch/fiscal series |
| `takeaway_queue_entries` | queue number และ public token ref | token hash เท่านั้น; อายุ/สถานะชัดเจน |
| `takeaway_kitchen_jobs` | งานตาม station | status transition แบบ monotonic ยกเว้น audited correction |
| `takeaway_pickup_handoffs` | ready/handed over | handoff ซ้ำคืนผลเดิม |
| `takeaway_offline_sync_receipts` | ผลรับ client envelope | envelope ID ไม่ซ้ำและ replay ได้ |

### Shift และ Replenishment

| ตารางเสนอ | หน้าที่ | Invariant สำคัญ |
| --- | --- | --- |
| `takeaway_shifts` | session การขายของ cashier/device | เปิดพร้อมกันตาม branch/device policy |
| `takeaway_shift_rounds` | snapshot รอบปิดกะ | round_no unique ต่อ branch+business_date |
| `takeaway_shift_round_items` | sold/replenishment snapshot | อ้าง order cutoff ที่ตรวจย้อนหลังได้ |
| `takeaway_central_orders` | ใบรายวัน/เพิ่ม/แก้ไข | regular unique ต่อ company+brand+branch+date |
| `takeaway_central_order_rounds` | เชื่อมหลายรอบปิดกะ | round เชื่อม regular order ได้ครั้งเดียว |
| `takeaway_central_order_items` | system/request/approve/ship/receive qty | unlisted line ต้อง resolve/reject ก่อน approve |

เสนอ `order_kind` เป็น `regular`, `extra`, `correction`:

- `regular` สร้างจากรอบปิดกะและมีได้หนึ่งใบต่อวัน/สาขา/แบรนด์
- `extra` ผู้มีสิทธิ์สร้างเพิ่มพร้อม reason และไม่แก้ regular snapshot
- `correction` ต้องอ้างเอกสารเดิมและได้รับอนุมัติจากส่วนกลาง

### Production, Stock และ Transfer

| ตารางเสนอ | หน้าที่ | Invariant สำคัญ |
| --- | --- | --- |
| `takeaway_production_batches` | แผน/สถานะผลิตต่อ output/recipe version | complete/cancel ทำซ้ำต้อง idempotent |
| `takeaway_production_batch_lines` | planned/actual input/output/waste | source lot และ UOM trace ได้ |
| `takeaway_stock_locations` | raw/ready/store/transit/waste | location ownership อยู่ company/branch ตาม type |
| `takeaway_stock_lots` | lot/expiry/unit cost | lot identity ไม่ซ้ำต่อ company+item+location |
| `takeaway_stock_balances` | projection ยอดเร็ว | ไม่ใช่ ledger source; rebuild จาก movement ได้ |
| `takeaway_stock_movements` | append-only stock ledger | unique source_type+source_id+line+movement_kind |
| `takeaway_stock_reservations` | reserve/release/consume | outstanding ห้ามติดลบ |
| `takeaway_transfers` | central → store shipment | state transition และ actor audit |
| `takeaway_transfer_items` | requested/shipped/received/discrepancy | received เกิน policy ต้อง approval |

วัตถุดิบร่วมหลายแบรนด์ใช้ `takeaway_stock_items` และ lot เดียวกันได้ เพราะ ownership อยู่
ระดับ Company+Location ขณะที่ `brand_id`, production batch และ recipe version ถูกเก็บบน
reservation/movement เพื่อแยกรายงานการใช้และต้นทุน ห้ามสร้าง balance ซ้ำเพียงเพราะคนละแบรนด์

### Franchise Credit

| ตารางเสนอ | หน้าที่ | Invariant สำคัญ |
| --- | --- | --- |
| `takeaway_credit_accounts` | บัญชีเครดิตต่อ brand+branch | account เดียวต่อขอบเขตและ currency |
| `takeaway_credit_ledger_entries` | append-only topup/reserve/capture/release/refund/adjust | entry amount แก้ย้อนหลังไม่ได้ |
| `takeaway_credit_reservations` | ผูกยอดจองกับ central order | capture+release ไม่เกิน reserved |
| `takeaway_credit_topup_requests` | QR/slip/review | review ซ้ำคืนผลเดิมและเก็บ reviewer |

ยอด balance/available/reserved เป็น projection ที่สร้างใหม่จาก ledger ได้ การปรับยอดต้องสร้าง
adjustment entry พร้อมเหตุผลและ approval ห้ามแก้ balance โดยตรง

### Integration และ Migration

| ตารางเสนอ | หน้าที่ | Invariant สำคัญ |
| --- | --- | --- |
| `takeaway_operational_outbox_events` | durable ERP/reporting handoff | idempotency key unique; transaction เดียวกับ source |
| `takeaway_inbox_receipts` | รับ Control Plane/ERP command event | event ID+consumer unique |
| `takeaway_import_batches` | dry-run/execute/result ของ Chambo import | source hash+contract version+status |
| `takeaway_import_issues` | mapping/validation/reconciliation issue | issue ต้อง resolve/accept ก่อน execute |

## Permission Namespace

ห้ามใช้ `brand.store.*` หรือ `fb.*` เป็น authorization หลักของ Takeaway ใหม่ ชุด permission
ที่ใช้งานจริงในรอบ dark launch คือ:

```text
takeaway.catalog.view
takeaway.catalog.manage
takeaway.sale.view
takeaway.sale.create
takeaway.sale.refund
takeaway.shift.manage
takeaway.kitchen.manage
takeaway.pickup.manage
takeaway.central_order.create
takeaway.central_order.manage
takeaway.production.manage
takeaway.stock.view
takeaway.stock.manage
takeaway.transfer.manage
takeaway.credit.manage
takeaway.report.view
takeaway.import.dry_run
takeaway.import.apply
takeaway.erp.export
takeaway.erp.acknowledge
```

Role preset ที่เชื่อมกับ Control Plane:

| Role | Scope | Permission หลัก |
| --- | --- | --- |
| `company-owner` | Company | ทุก Takeaway permission ตาม owner policy |
| `brand-manager` | Brand | catalog/central/production/stock/credit/report/ERP |
| `branch-manager` | Branch | sale/shift/pickup/central request/stock/transfer/report |
| `cashier` | Branch/Station | catalog view, sale create/view, shift และ pickup |
| `kitchen-staff` | Station | kitchen manage |

Manager override ต้องเป็น approval session แบบหมดอายุเร็วและเก็บ actor/reason ไม่ส่ง PIN
หรือ credential เข้า operational event

## ERP Event Contract Draft

### Envelope บังคับ

```json
{
  "event_id": "uuid",
  "event_type": "takeaway.sale.paid.v1",
  "schema_version": 1,
  "occurred_at": "ISO-8601 UTC",
  "idempotency_key": "stable-source-key",
  "company_id": "uuid",
  "brand_id": "uuid",
  "branch_id": "uuid-or-null",
  "aggregate_type": "takeaway_sale",
  "aggregate_id": "uuid",
  "payload": {}
}
```

Payload ห้ามมี access token, password, PIN, full payment credential หรือ PII เกินจำเป็น

### Event Types รอบแรก

| Event | สร้างเมื่อ | Consumer หลัก | Idempotency |
| --- | --- | --- | --- |
| `takeaway.sale.paid.v1` | payment และ stock issue สำเร็จ | Accounting/Consolidated Report | sale ID |
| `takeaway.sale.refunded.v1` | refund ที่อนุมัติ | Accounting/Report | refund key |
| `takeaway.shift.closed.v1` | ปิดรอบขาย | Operational Report | shift round ID |
| `takeaway.central_order.submitted.v1` | ส่งใบ regular/extra/correction | Central/Report | central order ID+revision |
| `takeaway.production.completed.v1` | complete batch และลง stock | Costing/Report | production batch ID |
| `takeaway.stock.moved.v1` | stock ledger เปลี่ยนจาก operation ที่อนุมัติ | Inventory/Report | movement ID |
| `takeaway.order.ready.v1` | Kitchen ทำครบทุก ticket | Queue/Pickup | order ID |
| `takeaway.order.picked_up.v1` | ส่งมอบสินค้า | Queue/Report | order ID |
| `takeaway.credit.changed.v1` | เครดิตเปลี่ยนจาก entry ที่อนุมัติ | Accounting/Report | credit entry ID |

ทุก event ถูกสร้างใน transaction เดียวกับ source document/movement/ledger และ consumer
ต้องเก็บ processed event ID ก่อน side effect เพื่อ replay โดยไม่ทำรายการซ้ำ

## API และ Route Boundary

Canonical UI ที่ implement แล้ว:

```text
/takeaway
/takeaway/counter
/takeaway/kitchen
/takeaway/pickup
/takeaway/central-orders
/takeaway/production
/takeaway/stock
/takeaway/transfers
/takeaway/credits
/takeaway/reports
/takeaway/import
/takeaway/erp
/takeaway/order/:token
/takeaway/pickup-status/:token
```

Canonical API prefix คือ `/api/v1/takeaway` และ public QR API คือ `/api/public/takeaway`.
Public QR API แยก token audience
จาก Restaurant และ resolve Company/Brand/Branch จาก server-side token record เท่านั้น

Legacy Chambo route อาจมีได้เฉพาะ redirect หลัง migration mapping ผ่านและต้องไม่กลายเป็น
default brand selector ของ SaaS

## Gate Tests ที่ต้องมีตั้งแต่ Work Package แรก

- unknown/restaurant/retail context เปิด Takeaway API ไม่ได้
- Takeaway context เปิด Restaurant operational API ไม่ได้
- database name ทั้ง legacy/Platform/Restaurant/Takeaway ไม่ซ้ำกัน
- Takeaway migration/backup/restore ทำงานโดยไม่แตะ database อื่น
- reference projector duplicate/out-of-order event ปลอดภัย
- cross-company/brand/branch access และ ID enumeration ถูกปฏิเสธ
- offline duplicate/concurrency/lost-ack ไม่สร้าง sale/payment/stock/event ซ้ำ
- stock movement/credit ledger/outbox append-only และ reconcile ได้
- Restaurant และ Retail regression ผ่านหลังเปิด Takeaway feature

## ลำดับ Implement หลัง Gate

1. เพิ่ม config/engine/session/readiness/migration boundary โดย feature ยังปิด
2. เพิ่ม reference projections และ fail-closed business-context tests
3. เพิ่ม catalog/order/payment/receipt/outbox vertical slice
4. เพิ่ม offline counter/shift/QR/kitchen/pickup
5. เพิ่ม replenishment/production/shared stock/transfer
6. เพิ่ม franchise credit และ consolidated reporting
7. ทำ Chambo dry-run importer, reconciliation, isolated restore และ UAT

## Implementation Update — 11 กันยายน 2026

- มี config, engine/session, fail-closed readiness, router, model และ Alembic chain แยกถึง
  `p6takeaway0004`
- มี operational model 30 ชนิด ครอบคลุม reference, catalog/recipe, shift/order/payment/receipt,
  ordering/pickup token, kitchen, central/production, stock/transfer, credit, outbox และ import archive
- public ordering token เก็บเฉพาะ hash, จำกัดอายุ/rate และไม่ใช้เลขออเดอร์เป็น secret; pickup status
  ใช้ token เฉพาะออเดอร์ที่สร้างจาก server secret
- customer QR order อยู่สถานะรอชำระและยังไม่ส่งครัว/ตัด stock จนพนักงาน capture payment
- device pairing/workspace รองรับ Takeaway context โดยไม่เปิด Restaurant operational session
- Chambo importer ผ่าน synthetic fixture, hash/idempotency/reconciliation และยืนยันว่า historical
  import ไม่สร้าง payment/ERP/notification side effect
- backup แยก `platform-core.dump`, `restaurant.dump`, `takeaway.dump` พร้อม SHA-256 และ restore
  ไปฐาน isolated ผ่านแล้ว
- ไม่มีการอ่าน/import Chambo production, ไม่มี UAT/Production deployment และ feature ปกติยังปิด

หลักฐานรวมอยู่ใน `P6-TAKEAWAY-IMPLEMENTATION-06.md`
