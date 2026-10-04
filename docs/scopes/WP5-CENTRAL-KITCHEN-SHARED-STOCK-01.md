# WP5-CENTRAL-KITCHEN-SHARED-STOCK-01 — ครัวกลางและวัตถุดิบร่วมหลายแบรนด์

วันที่วางแผน: 2026-09-14
วันที่ตรวจรับ local: 2026-09-14

สถานะ: **completed_local — WP5-A ถึง WP5-D ผ่าน automated local gate; ยังไม่อนุญาต UAT/Production activation**

Baseline: WP4 shared ERP/reporting local gate บน branch `codex/foodchainservice-platform`

## เป้าหมาย

ทำให้ครัวกลางของ Company รับคำสั่งผลิตจากหลาย Brand และตัดวัตถุดิบกองเดียวกันได้อย่างตรวจสอบย้อนหลังได้
เช่น “หมูแดดเดียว” กับ “หมูหนักย่าง” ใช้ `วัตถุดิบหมู` ตัวเดียว แต่แยกสูตร ผลผลิต ต้นทุน
คำสั่งผลิต และรายงานตาม Brand

```text
Company shared raw-material stock
└── Central Kitchen location / lot ledger
    ├── Brand A production order → Product A / Recipe A
    └── Brand B production order → Product B / Recipe B
```

## WP5-A — Current-state audit และ ownership contract

- ตรวจ stock location, recipe, production, replenishment และ central order เดิม
- กำหนด owner ของ shared ingredient, lot, inventory ledger, production order และ finished goods
- ระบุ migration mapping โดยไม่รวม stock balance เดิมแบบเดา
- ล็อกหน่วยนับ/conversion, costing method, negative stock และ timezone policy

## WP5-B — Shared ingredient identity

- Company-level canonical raw material ID หนึ่งตัวต่อวัตถุดิบจริง
- Brand recipe อ้าง canonical material เดียวกันได้ แต่สูตร/version/output ยังแยก Brand
- alias/SKU/supplier mapping ห้ามสร้างยอดคงเหลือซ้ำ
- active Company/Brand/Branch/Central Kitchen dimensions ต้องตรวจจาก server

## WP5-C — Demand, production และ stock ledger

- สาขาส่ง demand แยก Brand/Branch/source document
- ครัวกลางรวมแผนผลิตได้ แต่ production order และ finished goods ownership ยังระบุ Brand
- issue วัตถุดิบจาก location/lot กลางแบบ idempotent และ reversal ได้
- receive finished goods, transfer ไปสาขา, waste/yield variance และ costing มี audit trail
- concurrent production ห้ามตัดเกิน available balance หรือสร้าง ledger ซ้ำ

## WP5-D — UI, reporting และ gates

- Company Admin เห็น stock กลางและ demand รวม; Brand เห็นเฉพาะงาน/ผลผลิตใน scope
- drill-down จาก WP4 reporting dimensions ไป source production/stock document
- unit/API/concurrency tests สำหรับ multi-brand shared material, replay, reversal และ tenant isolation
- isolated migration/restore/downgrade rehearsal และ reconciliation เท่ากับ stock ledger ภายใน tolerance
- browser regression ผ่าน โดย Restaurant/Takeaway/Retail sale flow เดิมไม่เสีย

## นอกขอบเขต

- ไม่ย้าย Hotel หรือสร้าง Hotel PMS
- ไม่ import Chambo production data จริงในรอบ contract/migration rehearsal
- ไม่เปิด automatic purchasing, forecasting AI หรือ supplier integration ใหม่
- ไม่รวม finished goods คนละ Brand เป็น SKU เดียว
- ไม่ deploy หรือเปิดตัดสต๊อกจริงจน owner sign-off และ rollback drill ผ่าน

## Acceptance criteria

- [x] วัตถุดิบจริงหนึ่งตัวมี Company identity เดียวและหลาย Brand recipe อ้างร่วมได้
- [x] RAW issue/receive/reversal มี Company/location/lot/source; production และ finished Stock/Transfer ledger ระบุ Brand
- [x] replay ไม่ตัดซ้ำ และ concurrent production ไม่ทำให้ stock ติดลบเกิน policy
- [x] Brand A/B ใช้ stock หมูเดียวกัน แต่ finished goods/cost/report ไม่ปะปน
- [x] tenant/role/scope isolation ผ่าน
- [x] migration, restore, downgrade และ stock reconciliation ผ่านบนฐานชั่วคราว
- [x] backend/frontend/local browser regression ผ่าน; physical UAT คงพักตามคำสั่ง owner
- [x] ไม่มี UAT/Production activation โดยไม่ได้รับอนุมัติ

## Rollback

- ปิด shared production write path แล้วกลับไปใช้ Central Kitchen flow เดิม
- หยุด consumer/projector ก่อน rollback schema
- ledger ใหม่ห้ามถูกลบเงียบ; export manifest และ reconcile ก่อน restore
- operational sale และ WP4 reporting ต้องไม่ขึ้นกับการเปิด WP5

## Implementation decision

- shared RAW balance ใช้ `CompanyIngredientLot` เป็น authority ใหม่และไม่รวม Brand balance เดิมแบบเดา
- `CompanyKitchenMovement` เป็น append-only audit ledger พร้อม idempotency/reversal และ location identity
- production ใช้ Brand recipe เดิมผ่าน alias → canonical ingredient; output เข้า Brand READY `StockBalance`
- transfer finished goods ไปสาขา reuse Transfer/Stock ledger เดิม ไม่สร้าง transfer source of truth ซ้ำ
- API และ Company Admin page อยู่ที่ `/api/v1/company-kitchen/*` และ `/company-kitchen`
- read/report เปิดสำหรับตรวจ setup; write path ปิดด้วย `COMPANY_KITCHEN_WRITES_ENABLED=false`
- report ใช้ timezone ของ kitchen และ group ต้นทุน/ผลผลิตตาม Brand

Ownership และ rollout contract อยู่ที่ `docs/architecture/company-shared-kitchen.md`
หลักฐานตรวจรับอยู่ที่ `docs/scopes/WP5-PHASE-GATE-02.md`
