# WP7-PHASE-GATE-02 — Retail POS SaaS Alignment Verification

วันที่ตรวจรับอัตโนมัติ: 2026-09-15

สถานะ: **passed_local — Retail compatibility ทำงานต่อบน Legacy; Retail DB เป็น standby และยังไม่ deploy/activate**

Baseline rollback: WP6 commit `d9e4a728ef6316366a88e3e1592f268164aae846`

## สิ่งที่ส่งมอบ

- Retail physical database `retail_ops_db` และ Alembic chain แยกที่ `p7retail0001`
- server-owned `RETAIL_SERVICE_DATABASE=legacy|retail` พร้อม config/topology/schema fail-closed gates
- Product, Stock Count, POS และ Report connection routing สำหรับ Restaurant/Retail โดย Takeaway generic model API ถูกบล็อก
- Retail Counter device pairing ที่ผูก signed Company/Brand/Branch/`retail_pos` context และ entitlement
- Platform operations health, four-boundary migration, backup checksum และ isolated restore
- ownership/cutover manifest สำหรับ WP8 โดยไม่ copy ข้อมูลจริง

## Automated evidence

| Gate | ผล |
| --- | --- |
| Backend full regression | `312` tests ผ่าน |
| WP7 focused contract | database config/topology, routing, device token/type/entitlement และ Company Workspace tests ผ่าน |
| Retail migration | `base → p7retail0001 → base → p7retail0001`; current เป็น `p7retail0001 (head)` |
| Boundary metadata | `retail:1` ถูกต้องและแยกจาก Platform/Restaurant/Takeaway |
| Early cutover safety | ตั้ง Retail service ไปฐาน version 1 แล้ว startup readiness ปฏิเสธด้วย `not cutover-ready` |
| Four-boundary backup | Platform, Restaurant, Retail, Takeaway dumps พร้อม SHA-256 manifest |
| Isolated restore drill | restore ทั้ง 4 ฐาน, ตรวจ boundary identity และ cleanup ผ่าน |
| Frontend type/build | ผ่าน; production/PWA build `4,206` modules transformed |
| Browser regression | Platform/Workspace/entry routes `18/18` ผ่าน |
| Physical Retail UAT | พักตามคำสั่ง owner |
| UAT/Production activation | ไม่ได้ดำเนินการ; Retail runtime ปกติยัง `legacy` และ WP5/WP6 flags ยังปิด |

## Security และ boundary behavior

- Company Workspace และ device ไม่รับ Company/target database จาก client เป็น authority
- Retail devices รองรับ Counter เท่านั้น; Kitchen/Pickup ถูกปฏิเสธก่อนออก session
- Retail Counter ต้องผ่าน Company `retail_pos` entitlement และ token ถูกผูก credential generation
- generic Product/Report/Stock Count API ไม่ถูก route เข้า Takeaway schema
- Runtime cutover ต้องใช้ Platform identity/reference projector และชื่อฐาน Legacy/Platform/Restaurant/Retail
  ที่ไม่ซ้ำกัน
- schema version 1 ตั้งใจไม่มี operational tables และไม่สามารถรับ Retail traffic ได้

## คำเตือนที่ไม่บล็อก local gate

- Retail data ยังอยู่ Legacy; WP7 ไม่ได้พิสูจน์ data parity หรือ continuous reference projection
- scanner, printer, cash drawer และ offline field UAT ยังพัก
- production build มี large chunk warning เดิม ควรแก้ใน performance work package แยก
- test JWT key และ Starlette/httpx deprecation เป็น warning เดิม ไม่ใช่ production credential

## Rollback

1. ใช้ `RETAIL_SERVICE_DATABASE=legacy` ซึ่งเป็นค่า default
2. ถอด `RETAIL_DATABASE_URL` ได้โดย Retail POS เดิมยังใช้ Legacy
3. revert WP7 กลับ baseline WP6 หากต้องถอย source code
4. downgrade `p7retail0001 → base` เฉพาะฐาน standby ที่ไม่มีข้อมูลจริง
5. ห้ามสลับ UAT/Production ก่อน WP8 selective migration, parity, physical UAT และ owner sign-off

งานถัดไป: WP8 Retail Selective Data Migration และ bounded runtime canary โดยเริ่มจาก table/FK inventory,
reference projection receipt แยก, snapshot เฉพาะ Retail และ reconciliation; ยังไม่ควรเปิด UAT/Production
จนกว่าจะกลับมาทดสอบอุปกรณ์จริง
