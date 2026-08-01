# Scope ID: P4-RESTAURANT-ERP-ROUTING-05

สถานะ: **Verified — server-owned Restaurant ERP routing complete**

Phase: **Phase 4 — Restaurant ERP Core**

Business types: **restaurant routed to Restaurant DB; retail_pos remains legacy-compatible; takeaway remains unavailable**

Target database: **selected only from server-owned signed staff context**

## Problem

Stock, Purchase และ Transfer routers ยังใช้ legacy `get_db` ตายตัว แม้ Phase 1 จะมี Restaurant service database
และ signed `target_database` แล้ว หากเปิด Restaurant cutover routes เหล่านี้จะยังเขียน legacy database ขณะที่การย้าย
ทั้งหมดไป Restaurant แบบตายตัวจะทำให้ Retail ใช้ฐานผิดประเภท

## In Scope

- เพิ่ม operational DB dependency ที่เลือก connection จาก validated `TokenData.target_database`
- `restaurant` ใช้ `active_restaurant_service_session_factory()`
- `retail_pos` และ Company context ที่ยังไม่เลือก Branch คง legacy runtime เพื่อไม่ refactor Retail ใน Phase 4
- `takeaway` ปฏิเสธจนกว่าจะเริ่ม Phase 6
- Stock/Purchase/Transfer routers ใช้ dependency เดียวกันโดยไม่รับชื่อ database จาก client
- รักษา service/API contract และ permissions เดิม
- เพิ่ม routing unit tests และ cross-database guard regression

## Out of Scope

- Takeaway operational database/service
- Retail POS refactor หรือ migration
- production runtime cutover
- cross-business aggregate query; ใช้ reporting contract แทน

## Database / Ownership

- Restaurant Branch token มี `business_type=restaurant`, `target_database=restaurant` จาก Control Plane assignment
- Client header/query/body ไม่มีสิทธิ์เลือก database
- หนึ่ง request ใช้ operational session เดียวและไม่มี distributed transaction
- Restaurant stock/purchase/transfer records ไม่มี SQL FK ไป Retail/Takeaway database

## Acceptance

- [x] Restaurant Branch context เลือก Restaurant session factory
- [x] Retail context ยังคง legacy compatibility factory
- [x] Takeaway context ถูกปฏิเสธและไม่เปิด connection operational
- [x] Company context ที่ยังไม่เลือก Branch ไม่ถูกเดาเป็น Restaurant
- [x] Stock/Purchase/Transfer regression เดิมผ่านบน rollback-safe default
- [x] boundary test ยืนยันไม่มี client-controlled database selector

## Execution Record

- Routing unit tests ครอบคลุม Restaurant, Retail, Takeaway, Company และ unknown business context
- POS, Stock, Purchase และ Transfer ใช้ operational dependency จาก signed `TokenData`
- Restaurant operational boundary ไม่มี client header/query/body สำหรับเลือก database
- Backend regression 174 tests ผ่านบน rollback-safe legacy default
- หลักฐานรวมอยู่ใน `P4-PHASE-GATE-06`

## Rollback

- revert router dependency กลับ `get_db` ได้โดยไม่มี schema/data mutation
- runtime default ที่ `RESTAURANT_SERVICE_DATABASE=legacy` ยังคงพฤติกรรมเดิมตลอด Scope
