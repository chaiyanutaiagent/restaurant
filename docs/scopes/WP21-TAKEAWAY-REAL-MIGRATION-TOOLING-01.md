# WP21 — Takeaway Real Migration Tooling

วันที่: 2026-09-17

สถานะ: **implementation completed — ยังไม่มีการอ่านหรือนำเข้าข้อมูลจริง**

## ผลลัพธ์

- ตัวสร้าง snapshot อ่าน Chambo ผ่าน PostgreSQL transaction แบบ `READ ONLY` และ
  `REPEATABLE READ`, ปฏิเสธทันทีเมื่อมีกะ/ออเดอร์/การผลิต/โอน/เติมเครดิต/ตรวจนับที่ยังเปิด,
  ไม่ส่งออก credential หรือข้อมูลลูกค้า และสร้างไฟล์ normalized ตาม contract โดยไม่แก้ต้นทาง
- Exporter รับเฉพาะ normalized snapshot ที่ยืนยัน `read_only=true` และ `environment=approved_snapshot`
- Exporter ปฏิเสธการเขียนทับ bundle เดิม, canonicalize record, คำนวณ SHA-256/count/byte size และทำ artifact เป็น read-only
- Manifest ลงลายเซ็น Ed25519; importer เชื่อเฉพาะ `key_id` ที่ตั้งใน server secret environment
- Offline validator ตรวจ path escape, file hash, byte size, record count, mapping, schema/security และลายเซ็น
- Cutover preview ตรวจ company/brand จาก signed user context, source seal, open operation = 0, side-effect isolation, record totals และ control totals
- Execute endpoint ไม่มีค่า default และต้องส่ง preview digest เดิม, execution key, owner approval, final backup, rollback reference และคำยืนยันคงที่
- Cutover run เก็บแบบ immutable พร้อม import batch, source snapshot, digest, ผู้อนุมัติ และ reconciliation
- Import เดิมยังเปิดเฉพาะ synthetic; approved snapshot ใช้เส้นทาง cutover ที่มี gate แยก
- หน้า `/takeaway/admin/cutover` แสดง preview, blocker, approval evidence และประวัติ run

## Database

- Migration: `p6takeaway0007`
- ตารางใหม่: `takeaway_cutover_runs`
- ไม่มี foreign key หรือ query ข้าม Restaurant/Retail/legacy database

## การใช้งานเครื่องมือ

1. ผู้ดูแลข้อมูลสร้าง consistent source snapshot แบบ read-only ภายนอก runtime
2. ใช้ `python -m app.cli.snapshot_chambo_takeaway` พร้อม `CHAMBO_SOURCE_DATABASE_URL`
   และ mapping template ที่อนุมัติ เพื่อสร้าง normalized snapshot; URL ต้องส่งผ่าน environment เท่านั้น
3. ใช้ `python -m app.cli.export_chambo_takeaway` สร้าง bundle ใหม่พร้อม Ed25519 seal
4. ใช้ `python -m app.cli.validate_takeaway_import --public-key ... --key-id ...` ตรวจ offline
5. ส่ง payloadเข้า Preview และเก็บ digest เพื่อ owner review
6. Execute ได้เฉพาะเมื่อ backup/rollback/approval referenceครบ และ serverเชื่อ public keyนั้น

## Gate ที่ยังไม่ผ่าน

- ยังไม่ได้เชื่อม production Chambo database หรือ export ข้อมูลลูกค้าจริง
- ยังไม่ได้รัน approved snapshot กับ isolated target database
- ยังไม่มี owner/privacy/data approval หรือ production cutover

รายการจริงข้างต้นอยู่ WP25–WP26 และห้ามถือว่าเสร็จจากการมีเครื่องมือเพียงอย่างเดียว
