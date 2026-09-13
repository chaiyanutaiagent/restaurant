# WP5-CENTRAL-KITCHEN-SHARED-STOCK-01 — ครัวกลางและวัตถุดิบร่วมหลายแบรนด์

วันที่วางแผน: 2026-09-14

สถานะ: **next_planned — รอเริ่มหลัง WP4 gate; ยังไม่อนุญาต UAT/Production activation**

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

- [ ] วัตถุดิบจริงหนึ่งตัวมี Company identity เดียวและหลาย Brand recipe อ้างร่วมได้
- [ ] ทุก issue/receive/transfer/reversal มี Company, Brand, location, lot และ source identity
- [ ] replay ไม่ตัดซ้ำ และ concurrent production ไม่ทำให้ stock ติดลบเกิน policy
- [ ] Brand A/B ใช้ stock หมูเดียวกัน แต่ finished goods/cost/report ไม่ปะปน
- [ ] tenant/role/scope isolation ผ่าน
- [ ] migration, restore, downgrade และ stock reconciliation ผ่านบนฐานชั่วคราว
- [ ] backend/frontend/browser regression ผ่าน
- [ ] ไม่มี UAT/Production activation โดยไม่ได้รับอนุมัติ

## Rollback

- ปิด shared production write path แล้วกลับไปใช้ Central Kitchen flow เดิม
- หยุด consumer/projector ก่อน rollback schema
- ledger ใหม่ห้ามถูกลบเงียบ; export manifest และ reconcile ก่อน restore
- operational sale และ WP4 reporting ต้องไม่ขึ้นกับการเปิด WP5
