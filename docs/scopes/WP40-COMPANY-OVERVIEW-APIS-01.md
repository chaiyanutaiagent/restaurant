# WP40 — Company and Module Overview APIs

วันที่: `2026-09-19`
สถานะ: **Implemented locally — Production unchanged**

## Outcome

- เพิ่ม `GET /api/v1/company/overview` สำหรับ Company Dashboard แบบ role/scope-aware
- เพิ่ม `GET /api/v1/company/overview/{module_key}` สำหรับ ERP, Restaurant POS, Retail POS,
  Takeaway readiness, Central Kitchen และ Hotel planned state
- read model รวม context, task summary, module readiness, data source, operational status และ metric สำคัญ
- ทุก section มี `updated_at`, `status`, `stale` และ `error_code` contract
- หน้า `/company` ใช้ API รวมโดยตรง ไม่ join หลายสิบ endpoint ใน browser
- module ที่ไม่ effective, planned หรือ dark launch แสดง disabled และไม่สร้าง action ปลอม

WP นี้เป็น read API ไม่มี migration และไม่ย้าย system of record ของโมดูลใด
