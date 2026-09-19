# WP38 — Company Access, Owner Protection and Shell

วันที่: `2026-09-19`
สถานะ: **Implemented locally — Production unchanged**

## Outcome

- เพิ่ม role presets: Accountant, Purchasing, Warehouse, HR, Auditor, Area Manager, Service Staff และ
  Kitchen Manager โดยใช้ permission catalog เดิมและ scope แบบ Company/Brand/Branch/Station
- เพิ่ม policy ห้าม deactivate ผู้ใช้หรือ revoke assignment ของ Company Owner คนสุดท้าย พร้อม lock
  Company row ป้องกันคำขอพร้อมกัน
- Customer Company shell มีเมนูถาวร: หน้าหลัก, งานและการแจ้งเตือน, องค์กร,
  พนักงานและสิทธิ์, การตั้งค่า และแอปทั้งหมด
- route guard และ sidebar ใช้ permission source เดียวกันทั้งค่า `permission` และ `permissions`
- `/admin` และ `/:businessSlug/admin` เป็น role-aware landing แทนการส่งทุกบทบาทเข้าหน้าเดียว

High-risk action และ approval limit เดิมยังคงบังคับที่ backend; การซ่อนปุ่มไม่ถือเป็นการอนุญาต
