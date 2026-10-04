# P6-CHAMBO-DRY-RUN-05 — Import Reconciliation และ Rollback Plan

วันที่จัดทำ: 2026-09-11

สถานะ: **synthetic_validated — ยังไม่รันกับ production data**

## เป้าหมาย

พิสูจน์ว่า Chambo export bundle ถูกต้อง ปลอดภัย นำเข้า Takeaway Database ที่แยกออกมาได้
แบบทำซ้ำ และยอด master data, เงิน, Stock, เครดิต และเอกสารตรงกับ source evidence โดยไม่
เปลี่ยน Chambo source, Restaurant UAT หรือ production

## Preconditions

- Restaurant Completion Gate และ Platform Owner sign-off ผ่านก่อน execute importer
- source release/snapshot/cutoff ได้รับอนุมัติและเป็น read-only
- target เป็น isolated database ชื่อใหม่ ไม่ใช่ legacy/Platform/Restaurant/UAT/production
- contract/schema version และ target release commit ถูก pin
- mapping Company/Brand/Branch/Location ได้รับ data owner อนุมัติ
- backup source metadata และ target-empty baseline พร้อม checksum
- secret/PII/media policy และผู้รับผิดชอบ rollback ถูกระบุ

ในช่วงที่ Restaurant UAT ยังไม่ปิด อนุญาตเพียงสร้าง test plan/schema และทดสอบด้วย synthetic
fixture เท่านั้น ห้ามต่อ production database หรือสร้าง export จริง

## Dry-run Stages

### 1. Source Inventory — Read-only

บันทึกโดยไม่แสดง secret:

- source release commit และ migration head
- database snapshot identifier, generated time, cutoff UTC และ timezone
- Company/Brand/Branch ที่อยู่ใน scope
- row count และ distinct business key ต่อ section
- open order/shift/production/transfer/top-up และ pending operation count
- monetary/quantity control totals แยก branch/date/currency/UOM
- media file count/bytes และ source checksum

หากมี transaction หลัง cutoff ให้ excluded อย่างชัดเจนและห้ามรวมครึ่งเอกสาร

### 2. Export Bundle

- export จาก consistent snapshot เท่านั้น
- canonicalize records และคำนวณ record hash
- เขียนไฟล์ใหม่ใน empty directory; ห้าม overwrite bundle เดิม
- คำนวณ file SHA-256/bytes/record count แล้ว seal manifest
- run forbidden-field/secret/PII scan
- เปลี่ยน permission ของ artifact ให้เฉพาะ operator ที่ได้รับอนุญาต

### 3. Offline Validation

ตรวจโดยยังไม่ต่อ target database:

- manifest/mapping/ทุก NDJSON line ผ่าน JSON Schema
- SHA-256, byte size และ record count ตรง manifest
- source ID และ business key ไม่ซ้ำ
- parent/category/ingredient/location/branch reference resolve ครบ
- decimal, currency, UTC timestamp, business date และ UOM ถูกต้อง
- recipe ไม่มี loop, missing conversion หรือ effective range ซ้อน
- media MIME/size/hash ผ่าน policy
- forbidden credential/PII finding เป็นศูนย์

### 4. Target Preflight

- target database name ไม่ซ้ำกับฐานจริงทุกลูก
- Takeaway migration อยู่ expected head
- target Company/Brand/Branch reference projection ตรง approved mapping
- target operational tables ว่าง หรือ import batch เดิมอยู่ใน state ที่ retry ได้
- feature flag/route/worker ที่สร้าง side effect ยังปิด
- ERP consumers, payment provider, notification และ printer delivery ถูก disable/stub

### 5. Import to Isolated Database

ลำดับ import:

1. import batch + source/mapping/schema hashes
2. Control Plane reference validation
3. units/categories/items/brand links
4. stock locations/replenishment policy
5. recipes/ingredients/version ranges
6. historical archive ที่อนุมัติ
7. opening stock movements และ balance projection
8. opening credit ledger และ account projection
9. media metadata/files ที่ผ่าน scan
10. rebuild indexes/projections และสร้าง target summary

แต่ละ stage commit แยก checkpoint ตาม import batch แต่ห้ามเปิด runtime ระหว่างทาง

### 6. Idempotency Rehearsal

- รัน importer ด้วย bundle+mapping เดิมครั้งที่สอง
- ต้องคืน import batch/result เดิมหรือรายงาน `already_imported`
- row count, sum, movement, ledger, document และ event count ต้องไม่เพิ่ม
- เปลี่ยน bundle content แต่ใช้ export ID/hash เดิมต้อง fail
- bundle เดิมกับ mapping hash ใหม่ต้องสร้าง review ใหม่และห้าม execute อัตโนมัติ

### 7. Reconciliation

สร้าง `reconciliation-report.json` และรายงานอ่านง่าย โดยเทียบ source summary กับ target:

| Control | เกณฑ์ผ่าน |
| --- | --- |
| Unit/category/item/recipe/policy count | เท่ากันตาม included scope |
| Orphan/duplicate/cross-tenant reference | 0 |
| Recipe ingredient/yield totals | เท่ากันหลัง UOM canonicalization |
| Historical sale subtotal/discount/VAT/total/payment | เท่ากันต่อ branch+business date |
| Shift order count/amount | เท่ากับ sales ใน cutoff เดียวกัน |
| Central order requested/approved/shipped/received | เท่ากันต่อ document+line |
| Production input/output/waste | เท่ากันต่อ batch+item+UOM |
| Transfer sent/received/discrepancy/in-transit | เท่ากันต่อ document+line |
| Opening stock on-hand/reserved/value | เท่ากันต่อ location+item+lot+UOM |
| Credit ledger ending balance/reserved | เท่ากันต่อ brand+branch+currency |
| Import-created ERP/payment/notification side effect | 0 |
| Schema/hash/forbidden-data failure | 0 |

Money tolerance คือ `0.00` หลัง normalize เป็นหน่วยสตางค์ ปริมาณห้าม silently round; ต้องเท่ากัน
ตาม decimal places ของ UOM หรือถูกบันทึกเป็น approved exception

### 8. Functional Smoke ใน Isolated Environment

- เปิด brand/branch ด้วย mapped staff fixture
- ขาย paid-first และ retry client order ID เดิม
- ปิดกะสองรอบ ส่ง regular order และกดซ้ำ
- สร้าง extra order และ unlisted line แล้ว map/reject
- central approve/produce/pack/ship และ branch receive discrepancy
- franchise reserve/capture/release และ top-up approve ซ้ำ
- shared raw material ถูกตัดกองเดียวแต่รายงานแยก brand/batch
- QR → Kitchen optional → Pickup → Receipt → ERP outbox contract ผ่าน

### 9. Evidence และ Owner Review

Evidence directory ต้องมี:

```text
manifest.json
mapping.json
source-summary.json
validation-report.json
target-preflight.json
import-report.json
idempotency-report.json
reconciliation-report.json
smoke-report.json
rollback-report.json
approval-record.txt
```

Evidence ที่มี production-derived content ต้องอยู่นอก Git บน encrypted/access-controlled
storage ใน Git เก็บได้เฉพาะ template, schema และ redacted summary

## Hard Blockers

ห้าม execute/cutover หากพบข้อใดข้อหนึ่ง:

- checksum/schema mismatch หรือ bundle ถูกแก้หลัง seal
- secret, credential, unapproved PII หรือ unsafe media
- Company/Brand/Branch/Location mapping ไม่ครบหรือ cross-tenant
- duplicate SKU/unit/document/client order ID ที่ resolve ไม่ได้
- recipe loop/UOM conversion ขาด/effective version ซ้อน
- open shift/order/production/transfer/top-up ที่ไม่มี approved handling
- stock on-hand/reserved/value หรือ credit balance/reserved ไม่ตรง
- target importer สร้าง payment/ERP/notification side effect ระหว่าง history import
- idempotency rehearsal เพิ่ม record หรือยอดซ้ำ
- Restaurant/Retail regression ไม่ผ่าน

## Rollback

### Dry-run

1. ปิด isolated API/worker
2. เก็บ redacted failure evidence
3. ทำลายเฉพาะ isolated database ที่ resolve ชื่อและ owner แล้ว
4. bundle ต้นฉบับคง immutable; การแก้ข้อมูลสร้าง export ID ใหม่
5. Chambo source และ Restaurant databases ไม่ถูกเปลี่ยน จึงไม่มี application rollback

### Future Cutover

- สร้าง final source/target backup ก่อน mutation
- ปิด write ที่ Chambo ตาม approved downtime และตรวจ open document เป็นศูนย์
- import final delta ด้วย cutoff ใหม่และกระทบยอดซ้ำ
- เปิด Takeaway feature แบบ canary หนึ่ง branch
- หาก gate fail ให้ปิด feature/worker, คืน traffic ไป Chambo และ restore target จาก final backup
- ห้ามลบ Chambo source จนพ้น retention window และ owner ลงนาม

## Proposed Automation หลัง Gate

เครื่องมือต้องมี mode แยกชัดเจน:

- `inventory` — read-only summary
- `export` — สร้าง immutable bundle ใหม่
- `validate` — offline schema/hash/security validation
- `dry-run` — import เฉพาะ isolated database
- `reconcile` — สร้าง report โดยไม่แก้ข้อมูล
- `execute` — ต้องใช้ explicit confirmation, approved mapping และ production gate

`execute` ห้ามเป็น default และห้าม infer target database จาก environment ที่ไม่ระบุ

## Dry-run Acceptance Criteria

- [x] ระบุ preconditions, stage, hard blocker, evidence และ rollback แล้ว
- [x] กำหนด equality/tolerance ของเงิน ปริมาณ Stock และเครดิต
- [x] มี idempotency rehearsal และ side-effect isolation
- [x] source/UAT/production ไม่เปลี่ยนจากการจัดทำแผนนี้
- [x] synthetic fixture ผ่าน validator/importer หลัง implement โดย import รอบสองไม่เพิ่มข้อมูล,
  opening stock/credit ตรง และ historical side effect เท่ากับศูนย์
- [ ] approved Chambo snapshot ผ่าน dry-run หลัง Restaurant Completion Gate
- [ ] owner ลงนาม migration/cutover แยกต่างหาก
