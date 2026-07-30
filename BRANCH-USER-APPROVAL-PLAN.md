# แผนระบบขอเพิ่มผู้ใช้ประจำสาขาและอนุมัติก่อนใช้งาน

อัปเดตล่าสุด: 2026-07-21
สถานะ: **MVP implementation complete บน branch `codex/branch-user-approval`; รอ UAT และ deploy**

Implementation snapshot วันที่ 2026-07-21:

- เพิ่ม data model, migration และ permission แล้ว
- เพิ่ม backend request/approve/reject/cancel/resend/activate workflow แล้ว
- เพิ่มหน้าอนุมัติแยกแบรนด์ใน `/central/:brandSlug/staff`, หน้ารวม Super Admin ใน `/users` และหน้าคำขอของสาขาแล้ว
- คำขอใหม่เก็บ `brand_id`; backend ตรวจ Brand–Branch และจำกัดผู้อนุมัติทั่วไปไว้ที่ central branch ของแบรนด์
- คำขอใหม่รับ Username/Password ตั้งแต่หน้าสาขา เก็บเฉพาะ password hash และเปิดบัญชีทันทีเมื่อ Center อนุมัติ
- unit tests 11 รายการ, service smoke และ API end-to-end smoke ผ่านบนฐานข้อมูลทดสอบแยก
- migration จากฐานข้อมูลว่าง, downgrade และ re-upgrade ผ่าน
- frontend production build ผ่าน
- frontend typecheck ยังติดเฉพาะ error เดิม 4 จุดใน `RestaurantCentralStockPage.tsx` ซึ่งแก้แยกอยู่ใน PR #2
- รัน migration และเปิดระบบ local แล้ว; ยังไม่รัน migration กับ production และยังไม่ทำ UAT ครบทุก role ผ่าน browser

## 1. เป้าหมาย

ให้ผู้จัดการสาขาส่งคำขอเพิ่มพนักงานของสาขาตัวเองพร้อม Username/Password โดยบัญชียังใช้งานไม่ได้จนกว่าแอดมินกลางจะอนุมัติ หลังอนุมัติระบบสร้างบัญชีและพนักงานเข้าสู่ระบบได้ทันที

ผลลัพธ์ที่ต้องได้:

- ไม่มีการใช้บัญชีหรือรหัสผ่านร่วมกันในสาขา
- ทุกบัญชีถูกผูกกับ `company_id`, `branch_id` และ `role_id` ที่ตรวจสอบแล้ว
- ระบุผู้ขาย ผู้เปิดกะ และผู้ทำรายการได้จาก `user_id`
- สาขาเพิ่มได้เฉพาะพนักงานของตัวเองและเลือกได้เฉพาะบทบาทระดับสาขาที่แอดมินอนุญาต
- แอดมินอนุมัติเพียงครั้งแรก หลังเปิดใช้งานแล้วพนักงานล็อกอินเองได้
- การเปลี่ยนสาขา บทบาทระดับสูง หรือการเปิดบัญชีที่ถูกระงับ ต้องผ่านผู้มีสิทธิ์อีกครั้ง

## 2. สภาพระบบปัจจุบันที่ใช้เป็นฐาน

ระบบมีส่วนประกอบหลักอยู่แล้ว:

- `User` แยกผู้ใช้ตามบริษัท และมี `is_active`
- `UserBranch` ผูกผู้ใช้กับสาขาและบทบาท พร้อมสาขาเริ่มต้น
- สิทธิ์ถูกคำนวณจากบทบาทของผู้ใช้ในสาขาที่อยู่ใน token
- การสลับสาขาตรวจสอบ `UserBranch` ก่อนออก token ใหม่
- `UserInvitation` รองรับ OTP อายุ 72 ชั่วโมง
- หน้า `/accept-invitation` ให้ผู้รับคำเชิญตั้ง username และ password
- `CashierShift` เก็บ `branch_id`, `location_id` และ `user_id`
- `SaleOrder` เก็บ `branch_id`, `location_id`, `shift_id` และ `user_id`
- `Employee` มี `user_id` สำหรับเชื่อมข้อมูล HR กับบัญชีระบบ

ช่องว่างปัจจุบัน:

- ผู้มีสิทธิ์ `system.user.create` สามารถสร้างคำเชิญที่เปิดใช้งานได้ทันทีหลังผู้รับกรอก OTP
- ยังไม่มีสถานะคำขอ `pending` และขั้นตอนอนุมัติจากแอดมินกลาง
- ยังไม่มีข้อกำหนดระดับข้อมูลว่าบทบาทใดอนุญาตให้สาขาร้องขอได้
- หน้า Users เป็นมุมมองส่วนกลาง ยังไม่มีหน้ารายชื่อคำขอของสาขา
- OTP เดิมยังมีฟิลด์เก็บค่าต้นฉบับ จึงควรหยุดเก็บ plaintext สำหรับคำเชิญใหม่

## 3. ขอบเขต MVP ที่ตัดสินใจใช้

### อยู่ใน MVP

- ผู้จัดการสาขาส่งคำขอเพิ่มผู้ใช้
- แอดมินกลางดู อนุมัติ หรือปฏิเสธคำขอ
- แอดมินสามารถเปลี่ยนบทบาทเป็นบทบาทระดับสาขาที่ปลอดภัยก่อนอนุมัติ
- ผู้ขอกำหนด username/password ในฟอร์มตั้งแต่แรก โดย backend เก็บเฉพาะ password hash
- เมื่ออนุมัติ ระบบสร้าง `User` + `UserBranch` และเปิดใช้งานบัญชีใน transaction เดียว
- ระบบเชื่อม `User`, `UserBranch` และ `Employee` ถ้ามี employee ที่เลือกไว้
- แสดงสถานะและประวัติผู้ขอ/ผู้อนุมัติ/ผู้เปิดใช้งาน
- ป้องกันคำขอซ้ำและการข้ามสาขา
- คำขอเก่าที่ไม่มี credentials ยังใช้ invitation/OTP เป็น fallback ได้
- บันทึก audit log ทุกการเปลี่ยนสถานะ

### ยังไม่รวมใน MVP

- PIN สั้นสำหรับสลับพนักงานหน้าเครื่อง POS
- biometric, passkey หรือ SSO
- ให้พนักงานสมัครจากลิงก์สาธารณะโดยไม่มีผู้จัดการสาขาเป็นผู้ขอ
- อนุมัติอัตโนมัติ แม้จะเป็นบทบาทแคชเชียร์
- สร้างข้อมูลเงินเดือน/ภาษี/บัญชีธนาคารในขั้นตอนสมัคร
- ย้ายพนักงานข้ามสาขาแบบอัตโนมัติ

PIN สำหรับสลับคนขายหน้าเครื่องควรเป็น Phase ถัดไป เพราะต้องมีการ hash PIN, จำกัดจำนวนครั้งที่ลอง, lockout และ session ของเครื่องขายแยกจาก web login

## 4. ขั้นตอนธุรกิจ

```text
ผู้จัดการสาขา
    |
    | ส่งคำขอพนักงาน + บทบาท + Username/Password
    v
pending
    |-----------------------> rejected / cancelled
    |
    | Center อนุมัติและสร้างบัญชี
    v
activated
    |
    | login ด้วยบัญชีตัวเอง
    v
กะ / ออเดอร์ / รายงานระบุ user_id จริง
```

สถานะหลักของคำขอ:

- `pending` — รอแอดมินตรวจสอบ
- `approved` — ใช้เฉพาะคำขอเก่าที่ออกคำเชิญแล้วแต่พนักงานยังไม่เปิดใช้งาน
- `activated` — Center อนุมัติและสร้างบัญชีเรียบร้อย หรือคำขอเก่ารับคำเชิญสำเร็จ
- `rejected` — แอดมินปฏิเสธพร้อมเหตุผล
- `cancelled` — ผู้ขอหรือแอดมินยกเลิก

การหมดอายุเป็นสถานะของ invitation ไม่ใช่สถานะหลักของคำขอ หาก OTP หมดอายุ คำขอยังคง `approved` และแอดมินสามารถออกคำเชิญใหม่ได้ โดยคำเชิญเก่าต้องถูก revoke

## 5. กฎสิทธิ์และการแยกข้อมูลสาขา

เพิ่ม permission:

- `system.user.request` — ส่งคำขอและดูคำขอของสาขาปัจจุบัน
- `system.user.approve` — ดูและตัดสินคำขอทั้งบริษัท

คง permission เดิม:

- `system.user.create` — แอดมินสร้างผู้ใช้โดยตรงหรือสร้างคำเชิญโดยตรง
- `system.user.view`, `system.user.edit`, `system.user.delete` — จัดการผู้ใช้ที่เปิดใช้งานแล้ว

กฎบังคับใน backend:

1. ผู้ใช้ที่มี `system.user.request` ส่งคำขอได้เฉพาะ `current.branch_id`
2. ต้องมี `UserBranch` ที่ยัง active สำหรับสาขานั้น
3. ห้ามรับ `company_id` จาก payload ให้ใช้จาก token เท่านั้น
4. บทบาทที่ร้องขอต้องเป็นของบริษัทเดียวกันและ `is_branch_assignable = true`
5. บทบาทที่มีสิทธิ์ระดับกลาง เช่น user approval, role management, company settings, finance approval หรือ central stock management ต้องไม่ถูกตั้งเป็น branch-assignable
6. ผู้อนุมัติต้องมี `system.user.approve`; การเป็นผู้ขอเองไม่ทำให้อนุมัติคำขอเองได้
7. ห้าม approve คำขอที่ไม่ใช่ `pending`
8. ทุก transition ใช้ transaction และตรวจสถานะซ้ำในฐานข้อมูลเพื่อป้องกัน double approval
9. ผู้ใช้ใหม่ต้องมีสาขาเริ่มต้นเป็นสาขาที่ได้รับอนุมัติ
10. ผู้จัดการคนแรกของสาขาต้องให้แอดมินกลาง bootstrap เพราะยังไม่มีผู้ใช้ที่เชื่อถือได้ในสาขา

## 6. การเปลี่ยนแปลงฐานข้อมูล

### ตารางใหม่ `user_access_requests`

ฟิลด์ที่เสนอ:

| ฟิลด์ | รายละเอียด |
| --- | --- |
| `id` | UUID primary key |
| `company_id` | บริษัทเจ้าของคำขอ |
| `brand_id` | แบรนด์เจ้าของคำขอ; คำขอใหม่ต้องมีเสมอ |
| `branch_id` | สาขาที่จะผูกผู้ใช้ |
| `requested_role_id` | บทบาทที่สาขาร้องขอ |
| `approved_role_id` | บทบาทสุดท้ายที่แอดมินอนุมัติ |
| `employee_id` | optional; เชื่อมพนักงาน HR ที่มีอยู่ |
| `employee_code` | optional; ใช้ตรวจซ้ำ/ช่วยค้นหา |
| `requested_username` | Username ที่พนักงาน/ผู้ขอกำหนดก่อนส่งคำขอ |
| `initial_password_hash` | password hash ชั่วคราว; ล้างหลัง activate/reject/cancel |
| `first_name`, `last_name` | ชื่อพนักงาน |
| `email`, `phone` | ช่องทางส่งคำเชิญ อย่างน้อยหนึ่งรายการ |
| `request_note` | หมายเหตุจากสาขา |
| `status` | `pending`, `approved`, `activated`, `rejected`, `cancelled` |
| `requested_by` | ผู้ใช้สาขาที่ส่งคำขอ |
| `requested_at` | เวลาส่งคำขอ |
| `reviewed_by`, `reviewed_at` | ผู้ตรวจและเวลาตัดสิน |
| `review_note` | เหตุผลปฏิเสธหรือหมายเหตุอนุมัติ |
| `activated_user_id`, `activated_at` | บัญชีที่สร้างสำเร็จและเวลาเปิดใช้ |
| `created_at`, `updated_at` | เวลาอ้างอิงระบบ |

ดัชนีและ constraint:

- index `(company_id, status, created_at)` สำหรับคิวอนุมัติ
- index `(company_id, branch_id, status)` สำหรับหน้าสาขา
- index `(company_id, brand_id, status)` สำหรับคิว Center ของแต่ละแบรนด์
- unique partial index เพื่อป้องกันคำขอ `pending/approved` ซ้ำจาก employee เดียวกัน
- ตรวจว่าทุก foreign key อยู่ใน company เดียวกันใน service layer
- `employee_id` ที่ระบุต้องยัง active และอยู่สาขาเดียวกับคำขอ

### ปรับ `roles`

เพิ่ม:

- `is_branch_assignable: bool` ค่าเริ่มต้น `false`

แนวทาง migration:

- `store_cashier` ตั้งเป็น `true` ได้หลังตรวจรายการ permission
- role อื่นคง `false` จนกว่าแอดมินจะเลือกเปิดเอง
- หน้า Roles ต้องเตือนและห้ามเปิดค่านี้ถ้ามี permission ต้องห้าม

### ปรับ `user_invitations`

เพิ่ม:

- `access_request_id` nullable FK เพื่อรองรับคำเชิญเดิม
- `revoked_at` สำหรับยกเลิก OTP เก่าก่อนส่งใหม่

ปรับความปลอดภัย:

- หยุดเก็บ OTP plaintext สำหรับคำเชิญใหม่
- ช่วงเปลี่ยนผ่านให้ `otp_code` nullable และใช้ `otp_hash` เพื่อตรวจสอบ
- เพิ่ม `invitation_id` ใน request ตอนยืนยัน เพื่อ query คำเชิญตรงรายการแทนการไล่ตรวจ OTP ทุกแถว
- หลังหมดช่วงรองรับคำเชิญเก่า ค่อยสร้าง migration ลบ `otp_code`

## 7. API ที่วางแผนเพิ่ม

### ฝั่งสาขา

- `POST /api/v1/system/user-access-requests`
  - สร้างคำขอในสาขาปัจจุบัน
  - รับ `brand_slug` และตรวจว่าสาขาปัจจุบันเป็นสมาชิกที่ active ของแบรนด์
  - payload ไม่รับ `company_id`
  - `branch_id` ถ้ามีต้องตรงกับ `current.branch_id`; แนะนำไม่รับใน payload
- `GET /api/v1/system/user-access-requests/mine`
  - รายการของสาขาปัจจุบัน
  - บังคับ filter ด้วย `brand_slug`
  - filter: status, search, page, limit
- `GET /api/v1/system/user-access-requests/{request_id}`
  - สาขาดูได้เฉพาะของสาขาตัวเอง; แอดมินดูได้ทั้งบริษัท
- `POST /api/v1/system/user-access-requests/{request_id}/cancel`
  - ยกเลิกได้เฉพาะ `pending`
- `GET /api/v1/system/branch-assignable-roles`
  - คืนเฉพาะ role ที่สาขาสามารถร้องขอได้

### ฝั่งแอดมินกลาง

- `GET /api/v1/system/user-access-requests`
  - เมื่อส่ง `brand_slug` จะคืนเฉพาะแบรนด์และตรวจ central branch
  - เมื่อไม่ส่ง `brand_slug` จะเป็นรายการทั้งบริษัทสำหรับ Super Admin เท่านั้น
- `POST /api/v1/system/user-access-requests/{request_id}/approve`
  - รับ `approved_role_id` และ `review_note`
  - เปลี่ยนสถานะและสร้าง invitation ใน transaction เดียว
- `POST /api/v1/system/user-access-requests/{request_id}/reject`
  - บังคับกรอก `reason`
- `POST /api/v1/system/user-access-requests/{request_id}/resend-invitation`
  - revoke คำเชิญเดิมและสร้าง OTP ใหม่

### ปรับ API รับคำเชิญ

- `POST /api/v1/system/invitations/accept`
  - เพิ่ม `invitation_id`
  - ตรวจ invitation ยังไม่ใช้, ไม่ถูก revoke, ไม่หมดอายุ และคำขอต้นทางยัง `approved`
  - สร้าง `User` + `UserBranch`
  - ผูก `Employee.user_id` ถ้ามี employee ที่อนุมัติไว้
  - เปลี่ยนคำขอเป็น `activated`
  - ทำทั้งหมดใน transaction เดียว

ต้องรักษา backward compatibility สำหรับคำเชิญเดิมอย่างน้อยหนึ่งรอบ release ก่อนบังคับใช้ `invitation_id`

## 8. หน้าจอที่วางแผนทำ

### หน้าสาขา

เส้นทางเป้าหมาย:

- `/store/:brandSlug/branches/:branchCode/staff`

องค์ประกอบ:

- ปุ่ม “ขอเพิ่มพนักงาน”
- แสดงสาขาจาก route/token แบบ read-only
- ฟอร์มชื่อ นามสกุล employee เดิมหรือรหัสพนักงาน email/phone และบทบาท
- role dropdown แสดงเฉพาะ `is_branch_assignable`
- ตารางคำขอของสาขา พร้อม badge สถานะ
- ปุ่มยกเลิกเฉพาะรายการ `pending`
- แสดงเหตุผลเมื่อถูกปฏิเสธ
- ไม่แสดง OTP ให้ผู้ใช้ที่ไม่มีสิทธิ์อนุมัติ

ระหว่างที่ route แบบมี branch code ยังไม่เสร็จ สามารถเปิดหน้าเดียวกันจาก branch context ปัจจุบันได้ แต่ service ต้องยึด `current.branch_id` เป็นหลัก ไม่เชื่อ route ฝั่ง client

### หน้าแอดมินกลาง

ทางเลือกที่ใช้ใน MVP:

- เพิ่ม `/central/:brandSlug/staff` เป็นคิวอนุมัติประจำแบรนด์
- เก็บ tab “คำขอทุกแบรนด์” ใน `/users` สำหรับ Super Admin เท่านั้น

องค์ประกอบ:

- จำนวน pending ทั้งหมด
- filter สาขา สถานะ วันที่ และค้นหาชื่อ/เบอร์/email
- drawer/dialog ดูรายละเอียดผู้ขอและบทบาทที่ขอ
- เปลี่ยนเป็น role ที่ branch-assignable อื่นได้ก่อนอนุมัติ
- ปุ่มอนุมัติ ปฏิเสธ และส่งคำเชิญใหม่
- แสดงผู้ขอ ผู้ตรวจ เวลาตัดสิน วันหมดอายุ invitation และผู้ใช้ที่สร้างสำเร็จ

### หน้ารับคำเชิญ

ปรับ `/accept-invitation`:

- prefill company/invitation context จากลิงก์
- ผู้ใช้กรอก OTP, username, password และยืนยัน password
- ไม่แสดง Company ID แบบที่ต้องคัดลอกเอง เมื่อมีลิงก์ที่ถูกต้อง
- แจ้งสถานะหมดอายุ/ถูกยกเลิก/ถูกใช้แล้วแบบชัดเจน
- หลังสำเร็จ redirect ไป `/login`

## 9. การระบุคนขายและกะ

ส่วน POS รองรับ `user_id` อยู่แล้ว จึงไม่ควรสร้างฟิลด์ seller ซ้ำ:

- คนเปิดกะมาจาก `CashierShift.user_id`
- คนขายมาจาก `SaleOrder.user_id`
- สาขามาจาก `branch_id`
- จุดตัดสต็อกมาจาก `location_id`
- กะของรายการมาจาก `shift_id`

งานตรวจสอบเพิ่มเติมในขั้น implementation:

- ทุก endpoint สร้างออเดอร์จากหน้าร้านต้องใช้ `current.user_id` ไม่รับ seller จาก client
- shift ที่ส่งมาต้องเป็นของ user, branch และ company เดียวกับ token และยังเปิดอยู่
- รายงานออเดอร์ต้องแสดง `display_name` หรือ username ของผู้ขาย
- Restaurant/WAP order ที่ checkout ต้องคง `cashier_user_id` จาก sale order
- การเปลี่ยนคนขายหน้าเครื่องเดียวกันให้ logout/login ใน MVP; PIN switch แยกเป็น Phase ต่อไป

## 10. การเชื่อมกับ HR

หลักการ:

- บัญชีระบบกับประวัติพนักงานเป็นคนละ record แต่เชื่อมกันด้วย `Employee.user_id`
- ถ้าสาขาเลือก employee ที่มีอยู่ คำขอต้องบันทึก `employee_id`
- ตอน activate ให้ผูก `Employee.user_id` และคัดลอก `employee_code` ไป `User.employee_code`
- ถ้ายังไม่มี employee ให้สร้างเฉพาะบัญชีผู้ใช้ใน MVP ไม่สร้างข้อมูลเงินเดือนอัตโนมัติ
- ห้ามผูก user เดียวกับ employee มากกว่าหนึ่งคน
- employee ที่ยุติงานแล้วต้องไม่สามารถใช้คำขอใหม่ได้

## 11. Audit events

เพิ่ม event อย่างน้อย:

- `system.user_access.requested`
- `system.user_access.approved`
- `system.user_access.rejected`
- `system.user_access.cancelled`
- `system.user_access.invitation_resent`
- `system.user_access.activated`

metadata ควรมี:

- request id
- branch id
- requested role id
- approved role id
- requester/reviewer/activated user id
- สถานะก่อนและหลัง
- เหตุผลที่ปฏิเสธหรือยกเลิก

ห้ามบันทึก password, OTP plaintext หรือ token ลง audit log

## 12. ความปลอดภัยและ edge cases

- normalize username/email/phone ก่อนตรวจซ้ำ
- ตรวจ username ซ้ำใน company ตอน accept ภายใน transaction
- ตรวจ email และ employee code ซ้ำกับ user ที่ active และคำขอที่ยังค้าง
- rate limit การลอง OTP ตาม IP และ invitation id
- OTP ใช้ครั้งเดียวและหมดอายุ
- resend ต้อง revoke OTP เก่าก่อน commit OTP ใหม่
- ไม่เปิดเผยว่ามี username/email ใดในระบบผ่าน public error มากเกินจำเป็น
- revoke refresh tokens เมื่อ deactivate user หรือเปลี่ยนรหัสผ่าน
- access token เก่าหลัง deactivate ต้องถูกปฏิเสธจากการตรวจ active user หรือมีอายุสั้นตามนโยบายระบบ
- ไม่ให้ผู้ขอ approve คำขอของตัวเอง แม้จะถือ permission ทั้งสอง เว้นแต่เป็น superuser ตามนโยบายที่กำหนดชัดเจน
- ถ้า role ถูกปิด `is_branch_assignable` หลังส่งคำขอ ต้องไม่สามารถ approve ด้วย role นั้นได้
- ถ้าสาขาถูกปิด ต้องหยุดทั้งการส่งคำขอ การ approve และการ accept invitation
- ถ้าผู้ขอลาออก คำขอเดิมยังให้แอดมินตัดสินได้ แต่ต้องแสดงว่าผู้ขอ inactive
- double-click approve/accept ต้องให้ผล idempotent หรือคืน conflict โดยไม่สร้าง user ซ้ำ

## 13. ลำดับการพัฒนา

### Phase 1 — Data model และ permission

1. เพิ่ม model `UserAccessRequest`
2. เพิ่ม `Role.is_branch_assignable`
3. เพิ่ม `UserInvitation.access_request_id` และ `revoked_at`
4. สร้าง Alembic migration และตรวจ migration heads
5. seed `system.user.request` และ `system.user.approve`
6. กำหนด `store_cashier` เป็น branch-assignable หลังตรวจ permission
7. export model/schema ที่เกี่ยวข้อง

### Phase 2 — Backend workflow

1. เพิ่ม Pydantic schemas สำหรับ create/list/detail/approve/reject/cancel
2. สร้าง service แยกสำหรับ access request หรือแยกเมธอดจาก `AdminService` ให้ชัดเจน
3. บังคับ branch scope และ role allowlist ใน service
4. เพิ่ม endpoints ฝั่งสาขาและแอดมิน
5. เชื่อม approval กับ invitation เดิม
6. ปรับ accept invitation ให้ activate request และเชื่อม employee
7. เพิ่ม revoke/resend และ audit events
8. หยุดเก็บ OTP plaintext สำหรับ invitation ใหม่

### Phase 3 — Frontend admin

1. เพิ่ม types และ API client
2. เพิ่ม tab คำขอใน `/users`
3. ทำ filter/detail/approve/reject/resend
4. เพิ่มการตั้งค่า `is_branch_assignable` ในหน้า Roles พร้อม validation message
5. แสดงจำนวน pending ในเมนูหรือ tab

### Phase 4 — Frontend branch

1. เพิ่มหน้ารายชื่อพนักงาน/คำขอสาขา
2. เพิ่มฟอร์มส่งคำขอและเลือก employee เดิมได้
3. ใช้ branch จาก authenticated context
4. ผูก route เป้าหมาย `/store/:brandSlug/branches/:branchCode/staff`
5. เพิ่ม navigation จากพื้นที่หน้าร้าน

### Phase 5 — Invitation UX และ seller verification

1. ปรับลิงก์รับคำเชิญให้มี invitation context
2. รองรับคำเชิญเก่าในช่วงเปลี่ยนผ่าน
3. ตรวจ endpoint เปิดกะ/ขาย/checkout ว่าบังคับ user/branch/shift ถูกต้อง
4. แสดงชื่อคนขายในหน้ารายการและรายงานที่เกี่ยวข้อง

### Phase 6 — Test, migration rehearsal และ rollout

1. รัน backend unit/integration tests
2. รัน frontend typecheck/build
3. ทดสอบ migration ขึ้นและลงกับฐานข้อมูลทดสอบ
4. UAT ด้วยบัญชีแอดมิน ผู้จัดการสาขา และพนักงานใหม่
5. deploy backend migration ก่อน frontend
6. เปิด permission ให้ role ผู้จัดการสาขาหลังตรวจ UAT
7. ติดตาม failed OTP, duplicate request และ audit log หลัง deploy

## 14. แผนทดสอบ

### Backend tests

- ผู้จัดการสาขาสร้างคำขอในสาขาตัวเองได้
- สร้างคำขอข้ามสาขาไม่ได้
- เลือก role ที่ไม่ branch-assignable ไม่ได้
- ไม่มี permission แล้วสร้าง/ดู/อนุมัติไม่ได้
- Center อนุมัติคำขอใหม่แล้วสร้าง User/UserBranch เพียงหนึ่งชุดและไม่สร้าง invitation
- double approval ไม่สร้าง user หรือ invitation ซ้ำ
- reject ต้องมีเหตุผล
- ยกเลิกได้เฉพาะ pending และเฉพาะสาขาของตน
- OTP ผิด หมดอายุ ถูก revoke หรือใช้แล้ว ต้องไม่สร้าง user
- approval สำเร็จสร้าง User/UserBranch และ activate request ใน transaction เดียว
- invitation fallback ของคำขอเก่ายังตรวจ OTP/revoke/expiry ตามเดิม
- username/email/employee ซ้ำไม่สร้างข้อมูลครึ่งหนึ่ง
- employee ถูกผูกกับ user ถูกคนและถูกสาขา
- user ที่ยัง pending login ไม่ได้ เพราะยังไม่มีบัญชีจริง
- user ที่ activated login ได้และ token มี branch/permission ถูกต้อง
- deactivate user แล้ว refresh token ใช้ต่อไม่ได้

### Frontend tests/checks

- role dropdown ไม่มี role ระดับกลาง
- branch field แก้เองไม่ได้
- loading/error/empty states ครบ
- badge และ action เปลี่ยนตามสถานะถูกต้อง
- แอดมินเห็นข้อมูลข้ามสาขา แต่ผู้จัดการเห็นเฉพาะสาขาตัวเอง
- accept invitation แสดง error ที่เข้าใจได้
- responsive ใช้งานบนมือถือของสาขาได้

### UAT หลัก

1. แอดมิน bootstrap ผู้จัดการสาขา A
2. ผู้จัดการ A ขอเพิ่ม cashier A
3. ผู้จัดการ A พยายามเพิ่มคนให้สาขา B แล้วระบบปฏิเสธ
4. แอดมินเห็นคำขอ ตรวจ role และอนุมัติ
5. พนักงาน login ด้วย Username/Password ที่กำหนดในคำขอได้ทันที
6. พนักงานเปิดกะและสร้างออเดอร์
7. รายงานแสดงสาขา กะ และชื่อคนขายถูกต้อง
8. แอดมิน deactivate พนักงาน แล้วพนักงานเข้าใช้งานต่อไม่ได้

## 15. เกณฑ์รับงาน

งานถือว่าเสร็จเมื่อ:

- สาขาส่งคำขอได้โดยไม่สามารถสร้าง user ที่ active เอง
- ทุกคำขอต้องถูกจำกัด company/branch จาก token ฝั่ง server
- แอดมินอนุมัติหรือปฏิเสธได้ พร้อม audit trail
- สาขาเลือกได้เฉพาะ role ที่กำหนดเป็น branch-assignable
- Center อนุมัติแล้วพนักงาน login ด้วย credentials ที่กำหนดไว้ได้ทันที
- UserBranch, Employee (ถ้ามี), shift และ order เชื่อม user ถูกต้อง
- คำขอ/OTP ซ้ำ หมดอายุ และ resend ทำงานโดยไม่สร้างบัญชีซ้ำ
- backend tests, frontend typecheck/build และ migration rehearsal ผ่าน
- UAT ครบตามข้อ 14
- ไม่มี regression กับการสร้าง user/invitation เดิมของแอดมิน

## 16. ไฟล์ที่คาดว่าจะเกี่ยวข้องตอนเริ่มทำ

Backend:

- `backend/app/models/user.py`
- `backend/app/models/settings.py`
- `backend/app/models/role.py`
- `backend/app/models/hr.py`
- `backend/app/schemas/user_mgmt.py`
- `backend/app/services/admin_service.py`
- `backend/app/services/auth_service.py`
- `backend/app/routers/system.py`
- `backend/app/utils/seed_permissions.py`
- `backend/alembic/versions/`
- `backend/tests/`

Frontend:

- `frontend/src/pages/users/UsersPage.tsx`
- `frontend/src/pages/roles/RolesPage.tsx`
- `frontend/src/pages/auth/AcceptInvitationPage.tsx`
- `frontend/src/lib/adminApi.ts`
- `frontend/src/types/admin.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/layout/Sidebar.tsx`
- หน้าสาขาใหม่ภายใต้ `frontend/src/pages/restaurant/` หรือโครงสร้าง `store/` ที่จะกำหนดตอนทำ branch route

## 17. ลำดับความสำคัญเทียบกับงานหลายสาขา

ควรทำระบบนี้ก่อนเปิดใช้งานหลายสาขาจริง เพราะเป็นฐานของความรับผิดชอบรายบุคคลและ audit แต่ไม่ต้องรอการแยก stock หน้าร้าน/stock กลางให้เสร็จ เนื่องจากระบบนี้ยึด `branch_id` และสิทธิ์ผู้ใช้ ส่วนการตัด stock ยึด `location_id`

ลำดับที่แนะนำ:

1. ยืนยัน branch context และ route ที่มี branch
2. ทำ user request/approval/activation ตามแผนนี้
3. ตรวจ seller/shift audit ให้ครบ
4. แยก stock location หน้าร้านกับ stock กลาง
5. เพิ่ม PIN switch สำหรับเครื่องขาย หากหน้างานต้องสลับพนักงานบ่อย

## 18. จุดตัดสินใจก่อนเริ่ม implementation

ค่าเริ่มต้นที่แผนนี้เลือกไว้แล้ว:

- ทุกบัญชีต้องได้รับอนุมัติครั้งแรก ไม่มี auto-approve
- สร้าง `User` และเปิดใช้ตอน Center อนุมัติ; ก่อนอนุมัติเก็บเฉพาะคำขอและ password hash
- ใช้ password login เดิมใน MVP
- ใช้ `is_branch_assignable` ควบคุม role ที่สาขาเลือกได้
- ใช้ `/central/:brandSlug/staff` เป็นคิวอนุมัติประจำแบรนด์ และ `/users` เป็นหน้ารวม Super Admin
- เชื่อม Employee เมื่อมีข้อมูลเดิม แต่ไม่สร้างข้อมูล HR/เงินเดือนอัตโนมัติ

เรื่องที่เลื่อนไปตัดสินใจหลัง MVP:

- ส่ง OTP ผ่าน SMS, email หรือ LINE อัตโนมัติ
- ระยะเวลา OTP ที่ต่างจาก 72 ชั่วโมง
- PIN switch และ station session
- ให้ role แคชเชียร์อนุมัติอัตโนมัติในอนาคต
