# P6-CHAMBO-DATA-CONTRACT-04 — Versioned Export/Import Contract

วันที่จัดทำ: 2026-09-11

สถานะ: **synthetic_contract_implemented — ยังไม่ export production data**

Source baseline: `/Users/user/Projects/erp-pos-run` commit `15a1de1`

Contract version: `foodchainservice.takeaway-import/1.0.0-draft`

## เป้าหมาย

กำหนดรูปแบบข้อมูลกลางสำหรับนำความสามารถและข้อมูลที่ได้รับอนุมัติจาก Chambo เข้า
Foodchainservice Takeaway โดยไม่ copy database ตรง ๆ ไม่ย้าย credential และตรวจสอบจำนวน
ข้อมูล ยอดเงิน Stock เครดิต และ checksum ได้ก่อนเปลี่ยน runtime

## หลักการ

- export จาก consistent read-only snapshot ที่ระบุ cutoff time ชัดเจน
- ใช้ stable source ID สำหรับ trace แต่ target สร้าง ID ของตัวเองและเก็บ mapping
- จำนวนเงินและจำนวนสินค้าเก็บเป็น decimal string ห้ามใช้ floating point
- เวลาเก็บเป็น ISO-8601 UTC; business date เก็บแยกและระบุ timezone `Asia/Bangkok`
- ทุกไฟล์มี record count, byte size และ SHA-256 ใน manifest
- import ทุกครั้งมี import batch ID และ idempotency key
- master data, opening state และ historical archive แยก section ห้ามตีความปะปนกัน
- password, session, token, PIN hash, device credential, database URL และ secret ห้ามอยู่ใน bundle
- ไม่มี cross-database foreign key; mapping ไป Control Plane ใช้ canonical UUID ที่ operator อนุมัติ

## Bundle Layout

```text
takeaway-import-<export-id>/
  manifest.json
  mapping.json
  data/
    units.ndjson
    categories.ndjson
    items.ndjson
    recipes.ndjson
    replenishment-policies.ndjson
    stock-locations.ndjson
    opening-stock.ndjson
    opening-credit.ndjson
    historical-sales.ndjson
    historical-shifts.ndjson
    historical-central-orders.ndjson
    historical-production.ndjson
    historical-transfers.ndjson
    historical-credit-ledger.ndjson
    media-metadata.ndjson
  media/
    <content-addressed files approved for migration>
  reports/
    source-summary.json
    validation-report.json
    reconciliation-report.json
```

ไฟล์ที่ไม่มีข้อมูลยังต้องปรากฏใน manifest ด้วย `record_count=0` หรือถูกประกาศใน
`omitted_sections` พร้อมเหตุผล ห้ามหายไปโดยไม่ระบุ

## Machine-readable Schemas

- `docs/contracts/takeaway-import-manifest-v1.schema.json`
- `docs/contracts/takeaway-import-mapping-v1.schema.json`
- `docs/contracts/takeaway-import-record-v1.schema.json`

`manifest.json` และ `mapping.json` validate ตาม schema ของตัวเอง ส่วนแต่ละบรรทัดใน
`.ndjson` validate ด้วย record schema

## Section Classification

| Section | ประเภท | Default release แรก | หมายเหตุ |
| --- | --- | --- | --- |
| units | master | required | code/decimal places ต้องไม่ขัดกัน |
| categories | master | required | parent ต้องอยู่ในแบรนด์/Company เดียวกัน |
| items | master | required | menu/raw/ready/packaging และ brand visibility |
| recipes | master | required | รวม ingredient, version, yield, loss และ UOM |
| replenishment-policies | master | optional | map ตาม branch+item |
| stock-locations | master | required | central raw/ready/store/transit/waste |
| opening-stock | opening state | required เมื่อเปิด stock | signed balance ณ cutoff; ไม่ใช่ movement history |
| opening-credit | opening state | required สำหรับ franchise | signed ledger opening entry |
| historical-sales | archive | optional | ไม่มี customer PII โดย default |
| historical-shifts | archive | optional | ใช้รายงานย้อนหลัง ไม่เปิดกะใหม่ |
| historical-central-orders | archive | optional | open documents ต้องเป็นศูนย์ก่อน cutover |
| historical-production | archive | optional | ไม่ post stock ซ้ำ |
| historical-transfers | archive | optional | in-transit ต้องเป็นศูนย์หรือมีแผนเฉพาะที่อนุมัติ |
| historical-credit-ledger | archive | optional | ใช้ proof; opening-credit เป็นยอดเริ่มระบบใหม่ |
| media-metadata | media | optional | ไฟล์ต้องได้รับอนุญาตและผ่าน scan |

## Record Envelope

ทุกบรรทัด NDJSON ใช้ envelope เดียวกัน:

```json
{
  "record_type": "item",
  "source_id": "00000000-0000-0000-0000-000000000000",
  "source_updated_at": "2026-09-11T00:00:00Z",
  "source_hash": "64-character-lowercase-sha256",
  "data": {}
}
```

`source_hash` คำนวณจาก canonical JSON ของ `record_type`, `source_id` และ `data` โดย
sort key, UTF-8, ไม่มี insignificant whitespace และรักษา decimal เป็น string

## Canonical Mapping Rules

`mapping.json` เป็นไฟล์ที่ operator สร้างและอนุมัติแยกจาก source export:

- source Company → target canonical Company หนึ่งรายการ
- source Brand → target Brand ที่ `business_type=takeaway`
- source Branch → target Branch ภายใต้ Company/Brand เดียวกัน
- source User → target Control Plane User เฉพาะ actor ที่ต้องแสดงย้อนหลัง
- source Location → target Takeaway location หลังตรวจ physical ownership
- source SKU/Unit code ต้อง resolve ด้วย source ID + code ห้ามใช้ชื่อภาษาไทยเป็น key เดี่ยว

User ที่ไม่ map ให้ใช้ archived actor reference เช่น `legacy_actor:<source-id>` ในข้อมูลย้อนหลัง
ห้ามสร้าง login account อัตโนมัติ

## Field Mapping Decisions

### Brand/Branch

- `Brand.slug/name/storefront_mode/theme_config` เป็น candidate configuration
- `central_branch_id`, `central_location_id`, `central_ready_location_id` ต้อง map ใหม่
- `BrandBranch.branch_type` map เป็น `company_owned|franchise`
- target ownership มาจาก Control Plane; Takeaway DB เก็บ reference projection เท่านั้น

### Catalog

- `Unit.code/name/name_en/decimal_places` map เป็น unit master
- `Category.code/name/name_en/parent/sort_order` map เป็น category master
- `Product.sku/name/name_en/product_type/inventory_role/cost/selling_price/vat/UOM/status`
  map เป็น Takeaway item และ brand visibility
- product ที่ `brand_id IS NULL` ใน source ต้องมี explicit mapping ว่า shared กับแบรนด์ใดบ้าง
- barcode ซ้ำ, SKU ซ้ำหรือ UOM ไม่รู้จักเป็น blocker

### Recipe

- map `recipe_type`, `version_no`, effective range, yield quantity/unit, loss และ ingredient lines
- ingredient อ้างด้วย source product ID และ SKU
- target ต้องตรวจสูตรวน, missing conversion และ active range ซ้อนก่อน import
- recipe snapshot ที่ใช้กับ historical sale/production ไม่ถูกแก้เมื่อ master version เปลี่ยน

### Opening Stock

- ไม่ย้าย `stock_balances` เป็นตารางตรง ๆ; export เป็น signed opening-state records
- key คือ source branch/location/item/variant/lot + as-of time
- `qty_on_hand`, `qty_reserved`, `cost_per_unit` เป็น decimal string
- target สร้าง opening movement แบบ append-only อ้าง import batch และ source hash
- reserved quantity ต้องมี approved source document; หากไม่มีเป็น blocker

### Opening Credit

- export account limit, balance, reserved และ proof reference ณ cutoff
- target สร้าง opening ledger entry; ห้ามแก้ balance column โดยตรง
- reserved credit ต้องอ้าง open central order ที่ได้รับอนุมัติให้ย้าย มิฉะนั้นต้อง release/close ที่ source
- account+ledger ending balance/reserved ต้องเท่ากันก่อน export

### Historical Data

- เก็บ financial/document snapshots เพื่อรายงานและตรวจสอบ ไม่ replay side effects
- history import ไม่สร้าง payment charge, stock movement, credit movement หรือ ERP event ใหม่
- running document number ใหม่ใช้ target series; เลขเดิมเก็บเป็น `legacy_document_number`
- customer name/phone/tax ID ไม่รวมโดย default; หากต้องใช้ต้องมี owner/privacy approval แยก

## Privacy และ Security Filter

Exporter ต้อง fail หากพบ field/key หรือ value pattern กลุ่มต่อไปนี้:

- password, password hash, PIN/PIN hash
- access/refresh/session/device/pairing token หรือ credential
- API key, tunnel token, database URL, private key
- raw payment credential หรือข้อมูลบัตร
- customer PII ที่ไม่ได้อยู่ใน approved allowlist

Media ต้องตรวจ MIME จาก content, จำกัดขนาด, เปลี่ยนชื่อเป็น content hash และห้ามใช้ source
path เป็น target path โดยตรง

## Versioning Rules

- เพิ่ม optional field ที่ importer เก่า ignore ได้: minor version
- เปลี่ยนความหมาย field, required field หรือ decimal/date format: major version
- enum ใหม่ต้องระบุ fallback/compatibility; หากไม่มี importer ต้อง fail
- exporter/importer บันทึก schema version และ source/target release commit ใน evidence
- schema draft นี้ห้ามใช้ production จนถูกเปลี่ยนสถานะเป็น approved

## Proposed Tool Interfaces หลัง Gate

```text
scripts/export-chambo-takeaway.sh \
  --snapshot <approved-read-only-snapshot> \
  --brand chambo \
  --cutoff <ISO-8601> \
  --output <new-empty-directory>

scripts/validate-takeaway-import.sh \
  --bundle <bundle-directory> \
  --mapping <mapping.json>

scripts/import-takeaway-dry-run.sh \
  --bundle <bundle-directory> \
  --mapping <mapping.json> \
  --target-database <isolated-database-name>
```

เครื่องมือจริงต้องรับ credential ผ่าน environment/secret store และห้ามพิมพ์ลง log หรือ manifest

## Contract Acceptance Criteria

- [x] แยก manifest, mapping, records และ media ชัดเจน
- [x] มี schema version, cutoff, timezone, record count และ SHA-256
- [x] decimal/เวลา/ID มีรูปแบบ deterministic
- [x] แยก master/opening/archive และห้าม replay side effect จาก history
- [x] ไม่ย้าย identity/device/payment credential
- [x] รองรับหลาย Company/Brand/Branch และ stock item ร่วมหลายแบรนด์
- [x] มี machine-readable JSON Schema
- [ ] schema ผ่าน owner/data/privacy review
- [x] validator และ synthetic importer ถูก implement พร้อม hash/idempotency/reconciliation
- [ ] real exporter, approved Chambo snapshot และ production-derived dry-run รอ Restaurant Completion Gate
