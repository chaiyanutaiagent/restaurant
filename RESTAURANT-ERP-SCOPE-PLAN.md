# ERP POS Multi-Business SaaS — Scope and Delivery Plan

สถานะ: **ขอบเขตอ้างอิงก่อนเริ่มพัฒนารอบถัดไป**
วันที่จัดทำ: 31 กรกฎาคม 2026
เจ้าของการตัดสินใจผลิตภัณฑ์: Platform Owner
Repository: `chaiyanutaiagent/restaurant`

เอกสารนี้เป็นขอบเขตหลักสำหรับการพัฒนา Restaurant ERP แบบให้หลายกิจการเช่าใช้ระบบ (multi-tenant SaaS) มีไว้เพื่อป้องกันการเพิ่มฟังก์ชัน เปลี่ยนสถาปัตยกรรม หรือย้ายข้อมูลเกินกว่างานที่อนุมัติ

หากงานใดไม่สามารถอ้างอิงหัวข้อ เฟส และ Acceptance Criteria ในเอกสารนี้ได้ ให้ **หยุดและขออนุมัติ Scope Change ก่อนลงมือ**

---

## 1. เป้าหมายผลิตภัณฑ์

แพลตฟอร์มมีระบบขายมากกว่าหนึ่งรูปแบบ แต่การพัฒนารอบนี้ให้ทำ Restaurant ERP ให้เสร็จก่อน แล้วจึงพัฒนา Takeaway และจัดแนว Retail POS ในลำดับถัดไป ทั้งสามประเภทใช้ลำดับชั้นการเป็นเจ้าของแบบเดียวกัน แต่ใช้ operational database และ domain model คนละชุด

โครงสร้างผลิตภัณฑ์รวม:

```text
ERP POS Platform
└── Company (กิจการลูกค้า / Tenant)
    ├── Restaurant ERP       ← ลำดับพัฒนาปัจจุบัน
    ├── Takeaway             ← ทำหลัง Restaurant ผ่าน Go-live Gate
    └── Retail POS           ← ระบบขายสินค้าอื่นที่มีอยู่เดิม รักษา compatibility ไว้ก่อน
```

โครงสร้าง Restaurant ERP:

```text
ERP POS Platform
├── Platform Owner (เจ้าของระบบ)
└── Company (กิจการลูกค้า / Tenant)
    └── Restaurant ERP
        ├── Brand
        │   ├── Head Office / Central Kitchen (ถ้ามี)
        │   ├── Branch
        │   │   ├── Counter
        │   │   ├── Front of House
        │   │   ├── Kitchen
        │   │   ├── Stock Location
        │   │   └── Staff / Device
        │   └── Branch อื่น
        └── Brand อื่น
```

ลำดับการพัฒนาที่ล็อกไว้:

```text
1. Restaurant ERP: Phase 0–5 ให้เสร็จและผ่าน Owner sign-off
2. Takeaway System: Phase 6 ใช้ Control Plane มาตรฐาน แต่มี Takeaway operational database ของตัวเอง
3. Retail POS SaaS Alignment: Phase 7 ใช้ Control Plane มาตรฐาน และรักษา Retail operational database แยกจาก Restaurant/Takeaway
```

ห้ามพัฒนา Takeaway operational database หรือ refactor Retail POS ควบคู่กับ Restaurant Phase 0–5

ข้อมูลตั้งต้นที่ใช้อ้างอิงในการทดสอบรอบปัจจุบัน:

- Company: บริษัททดสอบปัจจุบัน
- Brand แรก: `ครัวป่า ปลาเขื่อน`
- Brand slug: `kruapa-pla-khuean`
- Branch แรก: `สาขากรุงเทพ` (`BKK-01`)
- Branch type: `company_owned`

ข้อมูลดังกล่าวเป็นข้อมูล tenant สำหรับทดสอบ ไม่ใช่ค่าที่ต้อง hard-code ลงใน business logic

---

## 2. หลักการแบ่งขอบเขตข้อมูล

### 2.1 Platform

เจ้าของระบบใช้สำหรับ:

- สร้าง ระงับ และดูแล Company
- ดูสถานะระบบ แพ็กเกจ การใช้งาน และเหตุการณ์ผิดปกติ
- ช่วยเหลือลูกค้าโดยมี Audit Log
- จัดการ feature flags และค่าระดับแพลตฟอร์ม

Platform Owner ต้องไม่ใช้หน้าจอเดียวกับ Company Owner และห้ามเข้าข้อมูลร้านโดยไม่มีเหตุผลที่บันทึกได้

### 2.2 Company

Company คือขอบเขต tenant สูงสุดของลูกค้า ข้อมูลทุกตารางทางธุรกิจต้องตรวจ `company_id` เสมอ

Company เป็นเจ้าของ:

- ผู้ใช้ บทบาท และการมอบหมายสิทธิ์
- Supplier และข้อมูลคู่ค้า
- การตั้งค่าบริษัท ภาษี และบัญชี
- Brand และ Branch
- รายงานรวมทุก Brand

### 2.3 Brand

Brand เป็นขอบเขตบริหารร้านอาหารภายใน Company

Brand เป็นเจ้าของหรือกำหนดมาตรฐาน:

- เมนูและหมวดหมู่เมนู
- สูตรอาหารและต้นทุนมาตรฐาน
- ราคาและโปรโมชั่นระดับแบรนด์
- รูปแบบบริการและมาตรฐานการปฏิบัติงาน
- คลังกลางหรือครัวกลาง (ถ้ามี)
- รายงานรวมของแบรนด์

### 2.4 Branch

Branch เป็นขอบเขตปฏิบัติการจริง

Branch เป็นเจ้าของ:

- โต๊ะ โซน และรอบการให้บริการ
- ออเดอร์ คิว งานครัว และการชำระเงิน
- กะเงินสดและการปิดกะ
- สต็อกและการนับสินค้าของสาขา
- พนักงานและอุปกรณ์ที่ได้รับมอบหมาย
- PromptPay ใบเสร็จ เครื่องพิมพ์ และการตั้งค่าเฉพาะสาขา

ข้อจำกัด MVP: **หนึ่ง Branch อยู่ได้หนึ่ง active Restaurant Brand เท่านั้น** การให้สถานที่เดียวขายหลายแบรนด์เป็น Future Scope และต้องออกแบบการแยกออเดอร์ สต็อก ราคา และอุปกรณ์ใหม่ก่อนเปิดใช้

### 2.5 Business Type

ทุก Brand ต้องมี `business_type` เพียงค่าเดียวและ Branch ทุกสาขาภายใต้ Brand ต้องสืบทอดประเภทนั้น

```text
restaurant | retail_pos | takeaway
```

กติกา:

- Company หนึ่งแห่งมีหลาย Brand ต่างประเภทกันได้
- Brand หนึ่งแห่งเปลี่ยน `business_type` ไม่ได้หลังมี operational data
- Branch ไม่สามารถเปิดหลาย `business_type` พร้อมกันใน MVP
- Staff assignment และ Device assignment ต้องระบุ Company, Brand, Branch และ `business_type`
- Role/permission ของแต่ละประเภทแยก domain กัน เช่น `restaurant.*`, `retail.*`, `takeaway.*`
- การย้าย Brand ไปอีกประเภทเป็น data migration project ที่ต้องมี Scope Change ไม่ใช่การแก้ setting

ตัวอย่าง:

```text
Company A
├── Brand ครัวป่า ปลาเขื่อน [restaurant]
│   └── สาขากรุงเทพ
├── Brand ร้านของฝาก [retail_pos]
│   └── สาขาหน้าร้าน
└── Brand ครัวด่วน [takeaway]
    └── สาขาบางนา
```

### 2.6 Database Boundary

ใช้ Control Plane กลางสำหรับ identity และ ownership เท่านั้น จากนั้นแยก operational database ตาม `business_type`

```text
platform_core database
├── companies
├── brands (มี business_type)
├── branches
├── users / identities
├── role assignments / scope / limits
├── device registry / assignment
├── module entitlements / feature flags
└── platform audit / support access

restaurant database
├── restaurant menu / recipe / ingredient mapping
├── tables / zones / dining sessions
├── restaurant orders / kitchen tickets / pickup queue
├── restaurant stock / purchase / production references
└── restaurant payments / receipts / operational audit

retail database
├── retail catalog / SKU / barcode / price
├── retail cart / sale / return / cashier shift
├── retail stock / purchase / transfer references
└── retail payments / receipts / operational audit

takeaway database
├── takeaway menu / option / price
├── takeaway order / queue / kitchen job / pickup
├── takeaway stock / purchase references
└── takeaway payments / receipts / operational audit
```

คำว่า “แยก database” ใน target architecture หมายถึงแยก PostgreSQL database หรือ datastore จริง ไม่ใช่เพียงเพิ่ม `business_type` ในตาราง order เดียวกัน

ข้อกำหนดการเชื่อมกัน:

- ห้ามสร้าง SQL foreign key ข้าม database
- ทุก operational record เก็บ immutable reference อย่างน้อย `company_id`, `brand_id`, `branch_id`
- Operational service ต้องตรวจ reference กับ Control Plane ผ่าน service/API หรือ signed context
- การส่งยอดขาย สต็อก การเงิน และรายงานข้าม domain ใช้ idempotent event/outbox หรือ versioned API
- ห้ามทำ distributed transaction ระหว่าง database
- Consolidated reporting ใช้ read model/reporting store หรือ API aggregation ไม่ใช้ cross-database join ใน request ปกติ
- แต่ละ database มี migration history, backup, restore, retention และ health check ของตัวเอง

ในระยะพัฒนาอาจใช้ PostgreSQL cluster เดียวกันได้ แต่ต้องเป็น database แยกและ connection/migration แยก เพื่อให้ย้ายเครื่องหรือ scale แยกภายหลังได้

---

## 3. ขอบเขตโมดูล

แต่ละ business type มี system of record ของตัวเอง แชร์ได้เฉพาะ Control Plane, identity, standards, libraries และ integration contracts ห้ามแชร์ operational tables

| Domain | System of Record | ขอบเขต |
|---|---|---|
| Company, Brand, Branch, Identity | Platform Control Plane | ownership และ authentication กลาง |
| Staff/Device Assignment | Platform Control Plane | scope กลางและ entitlement ตาม business type |
| Restaurant master/operations | Restaurant Database | เมนู สูตร โต๊ะ ออเดอร์ ครัว สต็อก กะ และใบเสร็จร้านอาหาร |
| Retail master/operations | Retail Database | SKU Barcode Sale Return Stock และกะ Retail |
| Takeaway master/operations | Takeaway Database | เมนู ออเดอร์ คิว ครัว Pickup Stock และกะ Takeaway |
| Consolidated reporting | Reporting Read Model | รับ event จากแต่ละ operational database |
| Platform audit/support | Platform Control Plane | การเข้าระบบและการช่วยเหลือ tenant |
| Operational audit/approval | Database ของแต่ละประเภท | เก็บรายการและ approval ของ domain นั้น |

อนุญาตให้ reuse source-code library หรือ UI pattern ได้ แต่คำว่า reuse ไม่อนุญาตให้ query/write operational database ของอีก business type โดยตรง

### 3.1 Restaurant Operations — In Scope

- รับออเดอร์ที่เคาน์เตอร์
- เปิดโต๊ะและ QR ต่อรอบ
- QR รับกลับที่ออกจากเคาน์เตอร์
- ลูกค้าสั่งอาหารและติดตามสถานะ
- Kitchen Display แยกงานรอทำ กำลังทำ และเสร็จแล้ว
- Pickup/Counter Display
- ส่งมอบอาหาร ออกบิล และชำระเงิน
- PromptPay QR และโลโก้บนใบเสร็จ
- ยกเลิก คืนเงิน และส่วนลดตามสิทธิ์อนุมัติ

### 3.2 Restaurant ERP Core — In Scope

- Dashboard ระดับ Company, Brand และ Branch
- จัดการ Brand และ Branch
- เมนู สูตรอาหาร และต้นทุนต่อจาน
- วัตถุดิบ หน่วยนับ และ Stock Location
- จัดซื้อ PO และรับสินค้า
- โอนสินค้าระหว่างคลัง/สาขา
- ครัวกลางและการผลิต เมื่อ Brand เปิดใช้
- เปิดกะ ปิดกะ และกระทบยอดเงิน
- รายงานยอดขาย ต้นทุน ของเสีย และกำไรขั้นต้น
- พนักงาน บทบาท ขอบเขต และประวัติการใช้งาน
- Audit Log และ Approval Flow สำหรับรายการสำคัญ

### 3.3 Retail POS เดิม — Compatibility Scope เท่านั้น

ระบบ Retail POS สำหรับขายสินค้าที่ไม่ใช่ร้านอาหารมีอยู่แล้วและต้องใช้งานต่อได้ตลอดการพัฒนา Restaurant

ระหว่าง Restaurant Phase 0–5 อนุญาตเฉพาะ:

- แก้ regression ที่เกิดจาก Restaurant changes
- รักษา Product, Stock, Sale, Payment, Shift และ Receipt contract เดิม
- เพิ่ม test เพื่อยืนยันว่า Restaurant ไม่ทำให้ Retail POS เสีย

ระหว่าง Restaurant Phase 0–5 ไม่อนุญาต:

- เปลี่ยน URL หรือ UX หลักของ Retail POS
- บังคับ Retail ทุกสาขาเข้า Brand model
- ย้ายหรือรวม SaleOrder ของ Retail กับ DiningOrder
- เพิ่มฟังก์ชัน Retail ใหม่ที่ไม่เกี่ยวกับ regression

Retail POS ใช้ Company/Brand/Branch/Staff/Device reference จาก Control Plane ได้ แต่ Product, Stock, Sale, Payment และ Shift ของ Retail ต้องอยู่ใน Retail Database และคง bounded context แยกจาก Restaurant/Takeaway

### 3.4 Takeaway — Deferred Scope

Takeaway ใช้ ownership hierarchy และ security pattern เดียวกับ Restaurant:

```text
Company → Brand → Branch → Staff/Device → Counter/Kitchen/Pickup
```

แต่มี Takeaway Database และ domain model ของตัวเอง ได้แก่ Takeaway menu, order, kitchen job, queue, pickup, stock, shift, payment reference และ receipt

อนุญาตให้ reuse UI component, validation library, payment adapter, printer adapter, event schema และแนวทางสิทธิ์จาก Restaurant ได้ แต่ห้ามอ่านหรือเขียน Restaurant operational tables โดยตรง การพัฒนา Takeaway เริ่มได้เฉพาะ Phase 6 หลัง Restaurant Go-live Gate ผ่าน

### 3.5 Out of Scope จนกว่าจะอนุมัติเพิ่ม

- Native iOS/Android application ใหม่
- Marketplace หรือระบบสั่งอาหารรวมหลายร้าน
- Delivery fleet และ route optimization
- AI พยากรณ์ยอดขายหรือสั่งซื้ออัตโนมัติ
- Loyalty/CRM ขั้นสูงและ marketing automation
- ระบบบัญชีแยกประเภทใหม่ที่ซ้ำกับ ERP Accounting เดิม
- ระบบเงินเดือนใหม่ที่ซ้ำกับ ERP HR เดิม
- Custom domain ต่อร้าน
- รองรับหนึ่ง Branch ขายหลาย Brand พร้อมกัน
- ระบบ Franchise royalty และสัญญาแฟรนไชส์เต็มรูปแบบ
- Subscription billing อัตโนมัติ ก่อน Tenant lifecycle พร้อม
- เปลี่ยนเทคโนโลยีหลักหรือแยก microservices

สำหรับ Phase 0–5 ให้ถือ “Takeaway standalone module” และ “Retail POS feature development” เป็น Out of Scope แม้ Phase 6–7 จะกำหนดไว้ล่วงหน้าแล้วก็ตาม

รายการ Out of Scope ทำได้เฉพาะเมื่อมี Scope Change ที่ระบุผลกระทบ ฐานข้อมูล API UI การย้ายข้อมูล และ UAT

---

## 4. ระดับพนักงานและสิทธิ์

สิทธิ์ต้องประกอบด้วยสามส่วนแยกกัน:

```text
Role  = ทำอะไรได้
Scope = ทำกับ Company / Brand / Branch ใด
Limit = ทำได้ภายใต้วงเงินหรือเงื่อนไขใด
```

ห้ามสร้าง Role ใหม่เพียงเพื่อฝังชื่อสาขา เช่น `Cashier-BKK` ให้ใช้ Role `Cashier` แล้วมอบหมาย Scope เป็นสาขากรุงเทพ

| Role preset | Scope ปกติ | หน้าที่หลัก |
|---|---|---|
| Platform Owner | Platform | ดูแล tenant และระบบทั้งหมด |
| Platform Support | Company แบบชั่วคราว | ช่วยเหลือโดยมีเหตุผลและ Audit Log |
| Company Owner | Company | อนุมัติและดูข้อมูลทั้งกิจการ |
| Company Admin | Company | ผู้ใช้ บทบาท Brand Branch และ ERP |
| Brand Manager | Brand | เมนู สูตร ราคา มาตรฐาน และรายงานแบรนด์ |
| Area Manager | หลาย Branch | ตรวจยอด สต็อก และอนุมัติรายการ |
| Branch Manager | Branch | จัดการร้าน กะ พนักงาน และสต็อกสาขา |
| Cashier | Branch/Counter | รับเงิน ออกบิล เปิดและปิดกะ |
| Service Staff | Branch | เปิดโต๊ะ รับออเดอร์ ย้ายโต๊ะ เรียกบิล |
| Kitchen Manager | Branch/Kitchen | จัดคิว ปิดงาน บันทึกของเสีย |
| Kitchen Staff | Kitchen station | เปลี่ยนสถานะเฉพาะงานครัว |
| Warehouse Staff | Stock Location | รับ โอน นับ และปรับสต็อกตามสิทธิ์ |
| Purchasing | Company/Brand | Supplier, PO และรับสินค้า |
| Accountant | Company | การเงิน ภาษี และรายงาน |
| HR | Company/Branch | พนักงาน กะ เวลา และเงินเดือน |
| Auditor | Assigned scope | ดูอย่างเดียวและตรวจ Audit Log |

พนักงานหนึ่งคนมีหลาย assignment ได้ เช่น Branch Manager ที่สาขากรุงเทพ และ Viewer ที่สาขาบางนา

### 4.1 Approval ขั้นต่ำที่ต้องรองรับ

- ส่วนลดเกินเพดาน Cashier ต้องใช้ Manager approval
- ยกเลิกหลังครัวเริ่มทำต้องระบุเหตุผลและได้รับอนุมัติ
- คืนเงินต้องอ้างอิงการชำระเดิมและเก็บ Audit Log
- ปรับสต็อกเกิน threshold ต้องได้รับอนุมัติ
- PO เกินวงเงินต้องส่งผู้มีสิทธิ์ระดับสูงกว่า
- การเปลี่ยน PromptPay ภาษี และบัญชีรับเงินต้องเก็บ before/after value

ห้ามใช้รหัสผ่านบัญชีผู้จัดการร่วมกัน ให้ใช้ Manager PIN/approval session ที่หมดอายุและตรวจย้อนกลับได้

---

## 5. URL และ Workspace ที่อนุมัติ

### 5.1 Platform Owner

```text
/platform
/platform/companies
/platform/companies/:companyId
/platform/audit
```

### 5.2 Company และ Restaurant ERP

```text
/app
/app/erp
/app/restaurant/brands
/app/restaurant/:brandSlug
/app/restaurant/:brandSlug/branches/:branchId
```

### 5.3 Branch Operations

```text
/app/restaurant/:brandSlug/branches/:branchId/counter
/app/restaurant/:brandSlug/branches/:branchId/orders
/app/restaurant/:brandSlug/branches/:branchId/tables
/app/restaurant/:brandSlug/branches/:branchId/kitchen
/app/restaurant/:brandSlug/branches/:branchId/pickup
/app/restaurant/:brandSlug/branches/:branchId/stock
/app/restaurant/:brandSlug/branches/:branchId/staff
/app/restaurant/:brandSlug/branches/:branchId/settings
```

### 5.4 Device Workspace

```text
/device/counter/:deviceToken
/device/kitchen/:deviceToken
/device/pickup/:deviceToken
```

Device token ต้องเพิกถอนได้ ผูก Company/Brand/Branch/Station ฝั่ง server และห้ามรับ scope จาก URL โดยไม่ตรวจฐานข้อมูล

### 5.5 Public Customer Routes

```text
/menu/:publicToken
/order/:publicToken
/status/:publicToken
```

Public token ต้องเดายาก หมดอายุได้ และไม่เปิดเผย UUID ภายในโดยไม่จำเป็น

### 5.6 Legacy Route Rule

Route ปัจจุบัน เช่น `/restaurant/orders` และ `/restaurant/kitchen` ต้องยังทำงานระหว่าง migration โดยใช้ redirect หรือ active context ห้ามลบทันทีจนกว่า UAT ของ canonical route จะผ่าน

### 5.7 Future Module Routes — จองรูปแบบไว้แต่ยังไม่ implement

หลัง Restaurant Completion Gate ผ่าน Takeaway ใช้โครง URL ขนานกับ Restaurant:

```text
/app/takeaway/brands
/app/takeaway/:brandSlug
/app/takeaway/:brandSlug/branches/:branchId/counter
/app/takeaway/:brandSlug/branches/:branchId/kitchen
/app/takeaway/:brandSlug/branches/:branchId/pickup
/app/takeaway/:brandSlug/branches/:branchId/settings
```

URL ต่างกันเพื่อให้ผู้ใช้เข้าใจ workspace และ backend ต้องชี้ไป Takeaway service/database โดยเฉพาะ อนุญาตให้ reuse library และ contract แต่ไม่ใช้ Restaurant operational database

Retail POS คง route เดิมในช่วง Restaurant Phase 0–5 ส่วน canonical route ของ Phase 7 ให้พิจารณาภายหลัง เช่น:

```text
/app/retail
/app/retail/branches/:branchId/pos
/app/retail/branches/:branchId/shifts
/app/retail/branches/:branchId/settings
```

รายการในหัวข้อนี้เป็น route reservation ไม่ใช่สิทธิ์ให้เริ่ม implement

---

## 6. Security และ Data Isolation — Non-negotiable

- ทุก business query ต้อง filter `company_id`
- Brand-owned data ต้องตรวจ `brand_id` หรือ resolve จาก Branch ที่ได้รับอนุญาต
- Branch operation ต้องตรวจ branch assignment ของผู้ใช้หรืออุปกรณ์
- Backend ต้องเลือก database จาก Brand/Branch `business_type` ที่ Control Plane ยืนยันแล้ว ห้ามให้ frontend ส่ง connection/database name
- Restaurant credential เชื่อมได้เฉพาะ Restaurant Database, Retail credential เชื่อมได้เฉพาะ Retail Database และ Takeaway credential เชื่อมได้เฉพาะ Takeaway Database
- ห้าม endpoint หนึ่งทำ SQL join หรือ transaction ข้าม operational database
- ห้ามเชื่อ `companyId`, `brandSlug` หรือ `branchId` จาก frontend เพียงอย่างเดียว
- Platform role และ Company role ต้องแยก permission domain
- Support access ต้องมีเหตุผล เวลาเริ่ม เวลาหมดอายุ และ Audit Log
- การอัปโหลดไฟล์ต้องตรวจชนิด ขนาด path และ tenant ownership
- Payment, refund, discount, void, stock adjustment และ settings สำคัญต้องมี Audit Log
- ห้ามใช้ test password หรือ default PIN ใน production
- Migration ต้อง rollback ได้หรือมี backup/restore procedure ที่ทดสอบแล้ว

---

## 7. แผนการพัฒนาแบบแบ่งเฟส

ห้ามเริ่มเฟสถัดไปก่อน Gate ของเฟสปัจจุบันผ่าน เว้นแต่ Platform Owner อนุมัติเป็นลายลักษณ์อักษร

### Phase 0 — Baseline และ Freeze

ขอบเขต:

- Commit งาน Restaurant ordering, kitchen, takeaway, payment QR, receipt logo และ Brand UI ปัจจุบัน
- บันทึก migration head และ backup ฐานข้อมูลทดสอบ
- ยืนยัน smoke test เดิมผ่าน
- ใช้เอกสารนี้เป็น scope baseline

คำว่า `takeaway` ใน Phase 0 หมายถึงการรักษา flow รับกลับที่มีอยู่ใน Restaurant เท่านั้น ไม่ใช่การเริ่มพัฒนา Takeaway business module

Acceptance Criteria:

- [ ] Working tree ของ baseline ไม่มีไฟล์ค้างโดยไม่ทราบที่มา
- [ ] Frontend type-check/build ผ่าน
- [ ] Backend tests ผ่าน
- [ ] Restaurant smoke flow ผ่าน
- [ ] มี commit hash สำหรับ rollback

### Phase 1 — Tenant, Brand และ Branch Foundation

ขอบเขต:

- บังคับความสัมพันธ์ Company → Brand → Branch
- เพิ่ม `business_type` ที่ Brand และให้ Branch สืบทอด
- เพิ่ม Staff/Device assignment ที่ระบุ business type และ target database
- บังคับ MVP rule หนึ่ง Branch ต่อหนึ่ง active Restaurant Brand
- จำแนกข้อมูล Company-owned, Brand-owned และ Branch-owned
- เพิ่ม validation ป้องกัน cross-tenant/cross-brand access
- วาง Control Plane Database และ Restaurant Database connection/migration boundary
- ห้าม Restaurant service ใช้ Retail operational tables เป็น system of record
- เพิ่ม canonical brand/branch context โดยยังเก็บ legacy routes

Acceptance Criteria:

- [x] Company A อ่านหรือแก้ Company B ไม่ได้ทุก API ที่ทดสอบ
- [x] ผู้ใช้เข้าถึง Brand/Branch นอก assignment ไม่ได้
- [x] Brand/Branch ที่เป็น `restaurant` เปิด Retail/Takeaway operational API ไม่ได้
- [x] ครัวป่า ปลาเขื่อนเปิดสาขากรุงเทพและเห็นข้อมูลเดิมครบ
- [x] Control Plane และ Restaurant Database backup/restore แยกกันได้
- [x] Legacy URL ยังทำงาน

Gate record: `P1-PHASE-GATE-08` ผ่าน isolated tenant/API matrix, retained-data check และ
Platform/Restaurant restore drill เมื่อ 1 สิงหาคม 2026 จึงเริ่มงาน Phase 2 ได้ภายใต้ Scope ID ใหม่
โดย production activation และการเปลี่ยน system of record ยังต้องอนุมัติแยกต่างหาก
Standalone Retail/Takeaway operational routers ยังไม่ถูกเปิดใน Phase 1; `/api/v1/pos` ปัจจุบันเป็น
legacy shared compatibility API และไม่ใช่ Retail Database API ของ Phase 7

ไม่รวม: Device pairing, subscription billing และ custom domain

### Phase 2 — Staff Roles, Scope และ Approval

ขอบเขต:

- Role preset ตามหัวข้อ 4
- User assignment ระดับ Company/Brand/Branch/Station
- Manager PIN/approval session
- Approval threshold สำหรับ discount, void, refund และ stock adjustment
- Audit Log พร้อม before/after value

Acceptance Criteria:

- [x] ทดสอบผู้ใช้จำลองอย่างน้อย Company Owner, Brand Manager, Branch Manager, Cashier และ Kitchen Staff
- [x] Cashier ทำรายการเกิน limit ไม่ได้โดยไม่มี approval
- [x] Kitchen Staff เข้าหน้าการเงินหรือ settings ไม่ได้
- [x] Audit Log ระบุผู้ทำ ผู้อนุมัติ สาขา เวลา และเหตุผลได้

ไม่รวม: HR/payroll engine ใหม่

Progress record: เริ่ม Phase 2 ด้วย `P2-ROLE-PRESETS-01` เมื่อ 1 สิงหาคม 2026 โดยย้าย preset
Company Owner, Brand Manager, Branch Manager, Cashier และ Kitchen Staff ไปเป็น versioned backend
policy/API และให้หน้า Roles ใช้ server contract เดียวกัน

`P2-SCOPE-ASSIGNMENTS-02` เพิ่ม Role scope contract และ assignment ระดับ
Company/Brand/Branch/Station พร้อม Station-locked token, granular kitchen-ticket permission,
create/revoke audit และ compatibility กับ `user_branches` เดิม โดยผ่าน isolated API matrix และ
Legacy/Platform migration rehearsal แล้ว

`P2-APPROVAL-SESSIONS-03` เพิ่ม Manager PIN ที่ hash พร้อม lockout, approval session แบบอายุสั้นและ
single-use ที่ผูก request fingerprint, limit enforcement สำหรับ discount/void/refund/stock, original
payment link และ approval audit โดยผ่าน API matrix และ migration rehearsal ครบทั้ง Legacy, Platform
และ Restaurant

Gate record: `P2-PHASE-GATE-04` ผ่าน consolidated persona/scope/approval matrix, migration
upgrade → downgrade → re-upgrade, backend 140 tests และ frontend type-check/build เมื่อ 1 สิงหาคม 2026
จึงปิด Phase 2 และเริ่ม Phase 3 ได้ภายใต้ Scope ID ใหม่ โดย production activation ยังต้องอนุมัติแยก
และ visual browser click-through ถูกเลื่อนเพราะ session ไม่มี in-app Browser instance

### Phase 3 — Dedicated Counter, Kitchen และ Device Pairing

ขอบเขต:

- Counter URL และ UI เฉพาะงาน
- Kitchen URL และ UI เฉพาะงาน
- Pickup display URL
- Device registration, pairing PIN/QR, revoke และ last-seen
- Samsung Galaxy Tab A11 LTE layout สำหรับครัวและเคาน์เตอร์

Acceptance Criteria:

- [x] Tablet ครัวเข้าได้โดยไม่ใช้บัญชี Company Owner
- [x] Tablet ที่ถูก revoke ใช้งานต่อไม่ได้
- [x] Counter, Kitchen และ Pickup เห็นเฉพาะ Branch ที่จับคู่
- [x] ทดสอบ offline/reconnect ขั้นพื้นฐานโดยออเดอร์ไม่ซ้ำ

ไม่รวม: Native mobile app และ MDM

Progress record: `P3-DEVICE-PAIRING-01` เพิ่ม Identity-owned device registry สำหรับ Counter/Kitchen/
Pickup, one-time PIN/QR, credential rotation, immediate revoke, last-seen และ server-owned
Company/Brand/Branch/Station context โดยผ่าน isolated API matrix กับ Legacy/Platform migration
rehearsal แล้ว Dedicated device workspaces และ offline/reconnect gate ยังทำต่อใน Scope ID ถัดไป

Gate record: `P3-PHASE-GATE-06` ผ่าน durable pairing, dedicated Counter/Kitchen/Pickup,
Counter staff handover/audit, signed offline authorization, migration rehearsal, backend 156 tests และ
frontend type-check/build เมื่อ 1 สิงหาคม 2026 จึงเริ่ม Phase 4 ได้ Physical tablet/Android UAT ถูก
Platform Owner เลื่อนไปเป็น follow-up และ production activation ยังคงต้องอนุมัติแยกต่างหาก

### Phase 4 — Restaurant ERP Core

ขอบเขต:

- Dashboard Company/Brand/Branch
- Menu/Recipe/Costing ระดับ Brand
- Stock/Purchase/Transfer ระดับ Company/Brand/Branch ใน Restaurant Database
- ส่ง event ไป consolidated accounting/reporting contract โดยไม่เขียน Retail/Takeaway Database
- Central kitchen/production เปิดใช้ตาม feature flag
- Shift reconciliation และรายงานยอดขาย/ต้นทุน/ของเสีย
- เชื่อม HR employee กับ assignment โดยไม่สร้าง payroll ใหม่

Acceptance Criteria:

- [x] Brand Manager เห็นข้อมูลรวมเฉพาะแบรนด์
- [x] Branch Manager เห็นเฉพาะสาขาที่ได้รับมอบหมาย
- [x] ต้นทุนเมนูคำนวณจากวัตถุดิบและหน่วยนับที่ตรวจสอบได้
- [x] การขายทำให้เกิด stock/payment/accounting handoff เพียงครั้งเดียว
- [x] Restaurant operational data ไม่มี SQL foreign key ไป Retail/Takeaway Database
- [x] รายงานรวมเท่ากับผลรวมรายการต้นทาง

ไม่รวม: AI forecast, advanced CRM และ franchise royalty

Progress record: `P4-REPORT-SCOPE-01` บังคับ Company/Brand/Branch assignment บน dashboard/report เดิม
แก้ Brand Manager consolidated-report permission, ป้องกัน Branch Manager ส่ง `branch_id` ข้าม assignment
และล็อก shift/PDF ตาม Branch โดยผ่าน API matrix, backend 162 tests และ frontend type-check/build แล้ว
Scope ถัดไปจึงขยาย Restaurant ERP dashboard/cost/reconciliation ต่อบน report boundary นี้ได้

Progress record: `P4-DASHBOARD-COSTING-02` เพิ่ม Brand operations dashboard, source reconciliation,
theoretical recipe COGS, waste cost และ cost provenance พร้อม strict unit conversion;
`P4-SALE-HANDOFF-03` เพิ่ม transactional outbox และ idempotent accounting source contract;
`P4-PRODUCTION-STAFF-04` เพิ่ม Brand production entitlement และบังคับ Active Employee link;
`P4-RESTAURANT-ERP-ROUTING-05` route POS/Stock/Purchase/Transfer จาก signed business context ไป
Restaurant operational session โดยไม่ให้ client เลือก database

Gate record: `P4-PHASE-GATE-06` ผ่าน migration upgrade → downgrade → re-upgrade ทั้ง Legacy,
Platform และ Restaurant, backend 174 tests, sale/staff/report/production/recipe API smokes และ frontend
type-check/build เมื่อ 1 สิงหาคม 2026 Live databases และ rollback-safe backend `latest` ไม่เปลี่ยน,
main backend คงหยุด และไม่มี production activation/deploy/push จาก gate นี้ จึงปิด Phase 4 ได้

### Phase 5 — Platform Onboarding และ Go-live

ขอบเขต:

- Platform console ขั้นต่ำสำหรับสร้าง/ระงับ Company
- Onboarding checklist: Company → Brand → Branch → Menu → Payment → Staff → Device
- Feature flags และ plan limit แบบ manual
- Backup, restore, monitoring, incident และ tenant export
- UAT และ production security review

Acceptance Criteria:

- [x] สร้างร้านลูกค้าใหม่โดยไม่แก้ source code หรือ SQL ด้วยมือ
- [x] ปิด Company แล้วทุก user/device ของ tenant เข้าไม่ได้
- [x] Backup/restore tenant test ผ่าน
- [x] UAT ตั้งแต่ QR order จนถึง ERP report ผ่าน
- [ ] Production checklist และ owner sign-off ครบ

ไม่รวม: ระบบเก็บเงิน subscription อัตโนมัติ

Progress record: `P5-TENANT-LIFECYCLE-01` เพิ่ม Platform Owner identity/workspace แยก,
Company + initial Company Owner onboarding, derived checklist, manual feature/limit controls,
audited suspend/reactivate และ Company credential generation ที่ revoke user/device รุ่นเดิมถาวร;
isolated Legacy/Platform/Restaurant migration rehearsal, backend `183` tests, lifecycle API smoke และ
frontend type-check/build ผ่าน โดยไม่ migrate/deploy production หรือเปลี่ยนฐาน live

Gate record: `P5-TENANT-RESILIENCE-02` เพิ่ม credential-redacted tenant export,
three-boundary backup/checksum, isolated restore drill, monitoring/webhook alert และ incident/recovery
evidence โดยผ่าน backend `185` tests, tenant API smoke, frontend type-check/build และ restore checksum
เมื่อ 1 สิงหาคม 2026 โดยไม่เพิ่ม migration ไม่แตะฐาน live และไม่มี production activation

Gate record: `P5-UAT-SECURITY-03` ผ่าน automated clean-room QR → Kitchen → payment →
recipe stock/accounting → ERP report UAT, exactly-once handoff, dine-in/takeaway และ role permission smoke,
backend `188` tests, frontend type-check/build, backend dependency audit, production API-doc disable,
nginx CSP/config และ repository safety เมื่อ 1 สิงหาคม 2026 โดยไม่มี production activation/deploy/push;
visual browser/device UAT, dependency risk acceptance และ owner sign-off ยัง pending

Gate record: `P5-COMPLETION-NONDEVICE-04` เพิ่ม Company Owner ใน Restaurant security matrix และ
explicit Retail POS compatibility ตั้งแต่ context → sale/payment → stock → accounting/outbox → report →
shift close พร้อมแก้ mixed central/store stock scope ของ Company Owner; isolated backend `189` tests,
role/approval smokes, Retail idempotency/reconciliation, frontend type-check/build และ repository safety ผ่าน
เมื่อ 1 สิงหาคม 2026 โดยไม่มี production activation/deploy/push

Gate record: `P5-PRODUCTION-READINESS-05` ผ่าน clean-room backend `189` tests และ QR → Kitchen →
served → bill/payment → stock/accounting/outbox → central report, standalone Chromium mobile/tablet
โดยไม่มี page/console/HTTP 5xx error, offline sync `100` orders แบบสอง batch และ lost-ack replay
โดยได้ canonical sale/payment/session/outbox/journal/stock เดิม, frontend type-check/build, backend audit
ไม่มี known vulnerability, frontend findings ไม่เกิน reviewed exceptions เดิม, readiness documents และ
repository safety เมื่อ 1 สิงหาคม 2026; physical-device UAT, security/operator/Platform Owner sign-off
ยัง pending ส่วน Draft PR CI ผ่านทั้ง push และ pull_request events แล้ว โดยไม่มี production activation,
live migration หรือ Phase 6 work

Owner สั่งเลื่อน physical/visual UAT จนกว่าอุปกรณ์จริงจะมาถึง งานที่เหลือคือ UAT ส่วนนั้น,
dependency risk acceptance, production checklist และ controlled owner sign-off ห้ามเริ่ม Phase 6,
deploy production, migrate ฐาน live หรือสร้าง Platform Owner บนฐาน live จนกว่าจะครบและมีคำสั่งชัดเจน

Owner อนุมัติให้เริ่มวางแผนย้าย Restaurant Server ก่อน Tablet UAT เมื่อ 9 สิงหาคม 2026 โดยให้
`docs/production/server-migration-plan.md` เป็น runbook สนับสนุนภายใต้ Scope
`P5-PHYSICAL-UAT-SIGNOFF-06` อนุญาตเฉพาะ read-only inventory, target preparation และ isolated
restore/UAT rehearsal ก่อน ส่วน live cutover, source shutdown, final domain switch และ production
activation ยังต้องมีคำสั่งอนุมัติแยกต่างหาก งานนี้ไม่ใช่ Takeaway Phase 6

Owner สั่งให้สลับไปใช้เครื่องใหม่เมื่อ 9 สิงหาคม 2026 จึงอนุมัติ controlled server cutover
ภายใต้ runbook ดังกล่าวแล้ว แต่ยังห้ามหยุด source จนกว่าจะมี target HTTPS route ที่ทดสอบผ่าน,
final backup/checksum, restore/reconciliation และ rollback path ครบถ้วน การอนุมัตินี้ไม่รวม
การเริ่ม Takeaway Phase 6 และไม่อนุญาตให้ลดความปลอดภัยของ Tablet เป็น public HTTP

Controlled cutover เสร็จเมื่อ 9 สิงหาคม 2026 โดยใช้ release `4c1c2ba` บน `mainserver`, restore
final backup และ migrate ถึง `p12route0014`; health, frontend, existing-user login และ auth/me
ผ่านทาง Tailnet HTTPS เครื่องเดิมหยุดเฉพาะ application containers แต่ยังเก็บ PostgreSQL, Redis
และ final backup สำหรับ rollback โดเมน `foodchainservice.com`, real SMTP, physical Tablet/printer
UAT และ owner completion sign-off ยังเป็นงานค้างของ Phase 5

UAT hostname เปิดเมื่อ 10 กันยายน 2026 โดยเชื่อม Tunnel `restaurant-uat` บน `mainserver` และ route
`https://uat-pos.foodchainservice.com` ไปยัง isolated UAT stack; Tunnel healthy, หน้าเว็บและ
`/health/live`/`/health/ready` ผ่าน HTTPS, browser ไม่มี console error และ response policy เป็น
`camera=(self)` แล้ว ต่อมา physical iPad เปิดกล้องและอ่าน test QR ผ่านเมื่อ 10 กันยายน 2026
ส่วน product/table business flow และ flow อื่นบน iPad/Printer จริงยัง pending

Owner อนุญาตให้ปิดขั้นตอน tenant login ชั่วคราวระหว่างทดสอบคนเดียวเมื่อ 10 กันยายน 2026 จึงเปิด
UAT Auto-login เฉพาะ `uat-pos.foodchainservice.com`; ระบบบังคับให้เป็น development HTTPS UAT,
Company และ tenant Superuser ที่ระบุชัดเจน ขณะที่ Production, Platform Owner และ device pairing
ไม่ถูก bypass ต้องปิดสวิตช์นี้ก่อน formal login/permission/pairing/revoke/security UAT และ sign-off

Physical iPad preflight รอบแรกเมื่อ 10 กันยายน 2026 พบว่า Chrome และ Safari ไม่มี native
`BarcodeDetector` ที่ POS เดิมบังคับใช้ จึงเพิ่ม ZXing fallback สำหรับ QR/EAN/UPC/Code 39/Code 128
และ deploy เฉพาะ UAT แล้ว Browser smoke เปิดหน้าต่างสแกนได้โดยไม่ขึ้น unsupported warning;
owner retest บน physical iPad เปิดกล้องและ decode `FCS-UAT-SCANNER-20260910` ได้สำเร็จ จึงผ่าน
camera/scanner preflight ส่วน product barcode และ table QR ใน business flow ยังต้องทดสอบต่อ

Progress record: `P5-POS-TABLET-UX-07` ปรับ Restaurant POS สำหรับ iPad landscape เป็นสามส่วน
หมวดสินค้า → สินค้า → ตะกร้า เพิ่มทางลัดเปิดโต๊ะ/QR, รับกลับ, พักบิล, ออเดอร์ QR และ KDS โดยใช้
route/permission เดิม เพิ่มสถานะเครื่อง/กล้อง/ซิงก์/การพิมพ์และ automated assertion ที่ 1024×768
โดยไม่แก้ database/backend และไม่แตะ Production ปุ่มเดลิเวอรีแสดงเป็น `รอเปิดใช้` เพราะยังไม่มี
Restaurant delivery order domain ใน Phase 5; source ผ่าน frontend type-check/build แล้ว ส่วน deploy และ
release `4100abb` deploy เฉพาะ UAT และผ่าน browser smoke ที่ 1024×768 แล้ว เมื่อ 11 กันยายน 2026
Cloudflare cache ถูกล้างเฉพาะ `https://uat-pos.foodchainservice.com/sw.js`; URL ตอบกลับแบบ `BYPASS`
พร้อม `no-store/no-cache` และ browser reload เปลี่ยนมาใช้ `/assets/index-CPB_Jgd2.js` สำเร็จ
โดยไม่ได้ใช้ Purge Everything ส่วน physical iPad business flow/printer UAT ยัง pending

Follow-up `P5-POS-WORKSPACE-THEME-08` เมื่อ 11 กันยายน 2026 รวม theme ของหน้าปฏิบัติการ POS
ให้หน้าโต๊ะ/QR, รับกลับ, ออเดอร์ QR, session detail/checkout และลูกค้าใช้ identity header,
navigation, background และ card language ชุดเดียวกับหน้าขาย; KDS ของพนักงานคง dark workspace
แต่ใช้ navigation ชุดเดียวกัน ขณะที่ device-only KDS ไม่เปลี่ยน และ delivery ยัง disabled
release `0a3642d` deploy เฉพาะ UAT frontend image `restaurant-pos-frontend:uat-pos-theme-0a3642d`
โดยเก็บ image `restaurant-pos-frontend:uat-tablet-v2-4100abb` และ backup source/env สำหรับ rollback
Browser smoke ที่ 1024×768 ผ่าน `/pos`, `/restaurant/tables`, `/restaurant/wap`,
`/restaurant/orders`, `/restaurant/kitchen` และ `/crm`; active workspace ถูกต้องและ document
horizontal overflow เป็น `0` ทุก route โดยไม่มี database/backend/Production change

Follow-up `P5-POS-TAKEAWAY-MERGE-09` เมื่อ 11 กันยายน 2026 รวมการขายรับกลับเข้า
`/pos?channel=takeaway` โดยใช้เมนูกลาง, ตะกร้า, ลูกค้า และการรับชำระหน้าเดียวกับ POS แต่ยังคง
order engine เดิมสำหรับเลขคิว, offline outbox, stock/accounting และลำดับสลิปลูกค้า → สลิปครัว →
KDS; `/restaurant/wap` redirect เข้าหน้าใหม่ ขณะที่ `/restaurant/wap/legacy` เป็น fallback ซ่อนสำหรับ
สิทธิ์เดิมและ rollback ส่วน Counter, Brand Store และ QR ลูกค้ายังคงเดิม release `c952f8d` deploy
เฉพาะ UAT frontend image `restaurant-pos-frontend:uat-pos-takeaway-c952f8d` และเก็บ image เดิม
`restaurant-pos-frontend:uat-pos-categories-47c583a` พร้อม backup source/env ที่
`/home/behappyaiagent/restaurant-uat-deploy-backups/c952f8d`; type-check/build, CI, backend unit
regression และ browser smoke บน UAT จริงผ่าน โดยหน้าใหม่แสดง 4 หมวด 16 เมนู, route redirect ถูกต้อง,
ไม่มี console error และ horizontal overflow ที่ 1024×768 เป็น `0`

Follow-up hardening `41d49d3` จำกัด UAT Auto-login ให้ทำงานเฉพาะ hostname `uat-*`, ปิด Service Worker
เฉพาะ Playwright เพื่อให้ API mock deterministic, เติม branch mock ที่ขาด และอัปเดต WeasyPrint เป็น
`70.0` พร้อม frontend dependency patches หลัง advisory ใหม่ โดย full isolated readiness gate ผ่าน
backend `232/232`, browser `14/14`, QR → Kitchen → payment → stock/accounting → ERP report,
offline reconnect/idempotency `100` orders, type-check/build, backend audit ศูนย์ known vulnerability,
frontend production audit ศูนย์ finding และ repository safety; deploy UAT เป็น backend/frontend image
`restaurant-pos-backend:uat-p5-hardening-41d49d3` และ
`restaurant-pos-frontend:uat-p5-hardening-41d49d3`, asset `/assets/index-BWeGI9bh.js`, health/redirect/PDF
runtime smoke ผ่าน พร้อม rollback backup `/home/behappyaiagent/restaurant-uat-deploy-backups/41d49d3`
และ image ก่อนหน้า โดยเหลือ physical Safari/iPad touch และ printer flow; Production ไม่ถูกเปลี่ยน

Next action record: งานที่จะกลับมาทำต่อใช้ Scope ID `P5-PHYSICAL-UAT-SIGNOFF-06`
ซึ่งยังเป็น Restaurant Phase 5 และมีสถานะ `in_progress` หลัง iPad scanner preflight ผ่าน
ลำดับงานที่ล็อกไว้คือ

1. ทำ read-only inventory ของ Restaurant source/target server, runtime database modes, backup topology, RPO/downtime และ owner โดยไม่บันทึก secret ลง Git
2. ซ้อม backup transfer/restore บน isolated target, ตรวจ checksum, migration heads, uploads, smoke และ reconciliation โดย source ต้องไม่เปลี่ยน
3. แก้และยืนยัน camera permission policy, เปิดเฉพาะ UAT hostname/Tunnel บน target แล้วตรวจ HTTPS/Tablet preflight
4. ยืนยันอุปกรณ์จริง, OS/browser/app, printer, network/UAT environment และผู้รับผิดชอบแต่ละ sign-off
5. ทำ physical dine-in/takeaway, pairing/revoke/restart/offline/lost-ack/printer และ ERP reconciliation UAT
6. หากพบ defect ให้แก้เฉพาะ approved failure scope แล้วรัน automated readiness/CI และ affected retest ซ้ำ
7. เมื่อ release candidate คงที่ ให้ refresh dependency audit และรับ Security Owner decision
8. ทำ operator incident drill, production/go-live checklist, backup/restore/monitoring/TLS/rollback review และ owner sign-off
9. รับ Platform Owner Restaurant completion approval แล้วจึงขอคำสั่งแยกสำหรับ server cutover/final domain, mark PR ready/merge, deploy หรือเริ่ม Phase 6

### Restaurant Completion Gate — ต้องผ่านก่อนเริ่มระบบอื่น

Restaurant ถือว่าเสร็จสำหรับเริ่ม Phase 6 เมื่อครบทั้งหมด:

- [ ] Phase 0–5 ผ่าน Acceptance Criteria
- [ ] ครัวป่า ปลาเขื่อนผ่าน UAT แบบ dine-in และรับกลับ
- [x] Role/Scope อย่างน้อย Owner, Manager, Cashier และ Kitchen ผ่าน security test
- [x] Restaurant ERP report กระทบยอดกับ order/payment/stock ได้
- [x] Backup/restore และ rollback ผ่าน
- [x] Retail POS regression suite ผ่าน
- [ ] Platform Owner ลงนามอนุมัติ Restaurant completion

สถานะ physical/visual UAT: **deferred by owner until hardware arrives**; automated dine-in/takeaway chain
ผ่านแล้ว แต่ยังไม่ใช้แทนการทดสอบ `ครัวป่า ปลาเขื่อน` บนอุปกรณ์จริงและไม่ใช้แทน owner sign-off

ข้อยกเว้นจาก Owner เมื่อ 11 กันยายน 2026: อนุญาตให้พัฒนา Phase 6 แบบ **dark launch**
ระหว่างพัก physical UAT ได้ โดยต้องคง `TAKEAWAY_FEATURE_ENABLED=false` ใน runtime ปกติ,
ไม่ deploy UAT/Production, ไม่อ่านหรือนำเข้าข้อมูล Chambo จริง และไม่ถือว่าแทน Restaurant
Completion Gate หรือ owner sign-off งาน activation/cutover ยังถูกบล็อกด้วย Gate เดิม

### Phase 6 — Takeaway System (หลัง Restaurant เสร็จเท่านั้น)

เป้าหมาย: เปิดระบบร้าน Takeaway ที่ใช้ Control Plane และมาตรฐานเดียวกับ Restaurant แต่มี Takeaway Database และ operational service ของตัวเอง

ขอบเขต:

- เพิ่ม Brand `business_type=takeaway` และ Branch ที่สืบทอดประเภท
- สร้าง Takeaway Database, migration chain, backup และ restore ของตัวเอง
- สร้าง Takeaway menu/order/queue/kitchen job/pickup/stock/shift/payment reference/receipt domain
- หน้า Counter สำหรับเปิดคิวและออก QR รับกลับ
- Customer QR ordering, Kitchen, Pickup และ Checkout บน Takeaway API
- Device pairing และ Staff Scope จาก Control Plane โดยใช้ `takeaway.*` permissions
- ใช้ UI/library/adapter ที่แชร์ได้โดยไม่ใช้ Restaurant operational tables
- ส่ง event ไป reporting/accounting contracts ที่กำหนด
- Onboarding template สำหรับร้าน Takeaway

Acceptance Criteria:

- [x] สร้าง Takeaway Company/Brand/Branch ได้โดยไม่แก้ source code หรือ SQL
- [x] Takeaway branch เปิด Restaurant/Retail operational API ไม่ได้
- [x] QR → Order → Payment → Kitchen → Pickup → Receipt → ERP event ผ่านแบบ automated
- [x] Takeaway order/stock/payment records อยู่ใน Takeaway Database เท่านั้น
- [x] Takeaway Database backup/restore และ migration ทำงานแยกจาก Restaurant/Retail
- [x] ข้อมูล Takeaway แยก Company/Brand/Branch และผ่าน cross-tenant test
- [x] Restaurant เดิมและ Retail POS regression ผ่านหลังเพิ่ม Takeaway system

Progress record: `P6-TAKEAWAY-IMPLEMENTATION-06` ทำ Takeaway แบบ dark launch ครบตั้งแต่
database/migration แยก, reference projection, `takeaway.*` permission, Counter/QR/Kitchen/Pickup,
paid-first payment, shift, central order/production, shared stock/transfer, credit, report, ERP outbox,
device workspace และ synthetic Chambo importer โดย backend `251` tests, frontend type-check/build,
end-to-end smoke, import idempotency และ checksum backup/isolated restore drill ผ่านเมื่อ 11 กันยายน 2026
ทั้งนี้ feature ปกติยังปิด ไม่มี UAT/Production deployment และ real Chambo migration, physical
tablet/printer/offline field UAT, activation/cutover และ owner sign-off ยัง pending

ไม่รวม: Delivery fleet, marketplace, aggregator integration และ native app

### Phase 7 — Retail POS SaaS Alignment (หลัง Restaurant เสร็จและ Scope Change อนุมัติ)

เป้าหมาย: จัด Retail POS เดิมให้ใช้ tenant/staff foundation มาตรฐาน โดยไม่เปลี่ยนให้เป็น Restaurant

ขอบเขตที่คาดการณ์ไว้:

- เพิ่ม/ยืนยัน `business_type=retail_pos` สำหรับ Brand/Branch ที่เกี่ยวข้อง
- Company/Brand/Branch access และ Role/Scope มาตรฐานจาก Control Plane
- Device pairing สำหรับเครื่องขายเมื่อจำเป็น
- Product, Barcode, Stock, Shift, Sale, Payment และ Receipt ใน Retail Database เท่านั้น
- แยก Retail connection/migration/backup/restore จาก database อื่นให้ชัดเจน
- Platform onboarding และ feature flags สำหรับ Retail tenant
- พิจารณา Brand scope สำหรับ Retail เป็นงานออกแบบแยก ไม่บังคับใช้จาก Restaurant โดยอัตโนมัติ

Acceptance Criteria ต้องจัดทำและอนุมัติใน Scope Change ของ Phase 7 ก่อนเริ่ม implement

ไม่รวม:

- Table, Dining Session, Kitchen Ticket และ Pickup Queue
- การรวม Retail SaleOrder กับ Restaurant DiningOrder
- การ query Restaurant/Takeaway operational database โดยตรง
- การเปลี่ยน Retail POS UX ครั้งใหญ่โดยไม่มี UAT แยก

Phase 7 เป็นแผนล่วงหน้า ยังไม่ถือว่าได้รับอนุมัติให้พัฒนา

---

## 8. Definition of Done สำหรับทุกงาน

งานหนึ่งถือว่าเสร็จเมื่อครบทั้งหมด:

- [ ] อ้างอิง Phase และ Scope ID ได้
- [ ] ระบุข้อมูล Company/Brand/Branch ที่ได้รับผลกระทบ
- [ ] ระบุ `business_type` และ target database ชัดเจน
- [ ] Backend permission และ ownership check ครบ
- [ ] Migration มี upgrade/downgrade หรือแผนกู้คืน
- [ ] ไม่มี cross-database query/transaction ที่ขัดกับ Database Boundary
- [ ] Unit/integration test ที่เกี่ยวข้องผ่าน
- [ ] Frontend type-check/build ผ่าน
- [ ] UAT flow ที่เกี่ยวข้องผ่าน
- [ ] ไม่ทำให้ legacy flow ที่ยังรองรับเสีย
- [ ] ไม่มี test credential, token หรือข้อมูลลับเข้า commit
- [ ] เอกสาร route/permission/operations ถูกอัปเดตเมื่อมีการเปลี่ยนจริง
- [ ] Commit มีขอบเขตเดียวและสามารถ rollback ได้

---

## 9. กติกาป้องกัน Scope Creep

ก่อนแก้โค้ดทุกครั้งต้องระบุ:

1. **Scope ID** เช่น `P1-BRAND-SCOPE-01`
2. **Problem** ปัญหาที่ต้องแก้
3. **In Scope** ไฟล์ API ตาราง และหน้าจอที่อนุญาต
4. **Out of Scope** สิ่งที่ตั้งใจไม่แตะ
5. **Acceptance Criteria** วิธีพิสูจน์ว่าเสร็จ
6. **Rollback** วิธีถอยกลับ

ทุก Scope ID ต้องระบุเพิ่มว่าเป็น `platform_core`, `restaurant`, `retail_pos` หรือ `takeaway` และห้ามแตะ database อื่นถ้าไม่ได้ระบุใน In Scope

ต้องหยุดและขออนุมัติเมื่อพบอย่างใดอย่างหนึ่ง:

- ต้องเพิ่มตารางหรือ service ที่ไม่อยู่ใน Phase
- ต้องแก้ permission domain นอกงาน
- ต้องเปลี่ยน URL public ที่มี QR ใช้งานอยู่
- ต้องลบหรือ rewrite ข้อมูลเดิม
- ต้องเปลี่ยน Git remote, deployment target หรือ production environment
- ต้องเพิ่ม third-party service หรือค่าใช้จ่ายใหม่
- ต้องขยายจากหนึ่ง Brand/Branch ไปกระทบทุก tenant โดยไม่มี migration plan
- ต้องสร้างฟังก์ชันที่อยู่ใน Out of Scope

ห้าม “ทำเผื่ออนาคต” ถ้ายังไม่มี Acceptance Criteria ในเฟสที่อนุมัติ

---

## 10. Scope Change Template

คัดลอกส่วนนี้เมื่อขอเพิ่มขอบเขต:

```md
## Scope Change: <ชื่อ>

- Requested by:
- Date:
- Current phase:
- Reason:
- User outcome:
- In scope:
- Out of scope:
- Data model impact:
- Business type / target database:
- API impact:
- UI/URL impact:
- Permission/security impact:
- Migration/rollback:
- Tests/UAT:
- Estimated delivery slices:
- Owner approval: Pending / Approved / Rejected
```

ห้ามเริ่ม implement จน `Owner approval` เป็น `Approved`

---

## 11. งานถัดไปที่อนุญาต

งานถัดไปหลังเอกสารนี้ได้รับการยืนยันคือ **Phase 0 — Baseline และ Freeze เท่านั้น**

ลำดับที่อนุญาต:

1. ตรวจ diff และแยกงานปัจจุบันออกจากงานสถาปัตยกรรมใหม่
2. ทดสอบ Restaurant flow ปัจจุบัน
3. Commit baseline พร้อม commit hash
4. Backup ฐานข้อมูลทดสอบ
5. จัดทำ Scope ID แรกของ Phase 1 และขออนุมัติก่อนแก้โค้ด

ยังไม่อนุญาตให้ refactor URL, permission, tenant model หรือ device authentication จน Phase 0 ผ่าน และห้ามเริ่ม Takeaway Phase 6 หรือ Retail Phase 7 ก่อน Restaurant Completion Gate

---

## 12. Related Documents

- `RESTAURANT-MODULE-PLAN.md` — แผน F&B operations เดิม
- `RESTAURANT-OPERATIONS-GUIDE.md` — คู่มือการใช้งานร้านอาหาร
- `UAT-RESTAURANT.md` — UAT flow ร้านอาหาร
- `UAT-POS.md` — UAT และ regression ของ Retail POS
- `docs/architecture/modules.md` — ขอบเขตโมดูลเดิม
- `docs/architecture/permissions.md` — permission และ role presets เดิม
- `docs/architecture/routes.md` — route plan เดิมและ legacy route rule

เมื่อข้อมูลขัดกัน ให้ใช้เอกสารนี้สำหรับขอบเขต SaaS และใช้เอกสารเดิมสำหรับรายละเอียดฟังก์ชันที่ไม่ขัดกับขอบเขตนี้

---

## 13. Approval Log

| Version | Date | Decision | Approved by |
|---|---|---|---|
| 0.1 | 2026-07-31 | Initial scope draft | Pending |
| 0.2 | 2026-07-31 | ล็อกลำดับ Restaurant → Takeaway → Retail POS alignment | Pending |
| 0.3 | 2026-07-31 | แยก Control Plane และ operational database ตาม business type | Approved by Platform Owner |

---

## 14. Foodchainservice Platform Restructure Decision

ตั้งแต่ 13 กันยายน 2026 ใช้ชื่อผลิตภัณฑ์ `Foodchainservice` และชื่อโครงการเป้าหมาย
`Foodchainservice Platform` โดยจัด Customer Register / Company Admin เป็นทางเข้ากลาง แล้วแยก
Restaurant POS, Takeaway POS, Retail POS และ Hotel PMS เป็นโมดูลบริการ ภายใต้ ERP, รายงานรวม,
Central Kitchen และ Supply Chain ที่ใช้ร่วมกันตาม contract

WP0 เป็น baseline ก่อนปรับโครงสร้างและแทนลำดับ “งานถัดไป” ในหัวข้อ 11 เท่านั้น
กติกา tenant isolation, database boundary, permission, audit และ scope control ในเอกสารนี้ยังคงใช้
จนกว่าจะมี Scope Change ที่อนุมัติอย่างชัดเจน

หลักฐาน WP0 อยู่ที่ `docs/scopes/WP0-FOODCHAINSERVICE-PLATFORM-BASELINE-01.md`

แผนงานถัดไปอยู่ที่ `docs/scopes/WP1-PLATFORM-SHELL-MODULE-MAP-01.md` โดย WP1 จำกัดอยู่ที่
product identity, module map และ shared entry shells เท่านั้น ยังไม่เปลี่ยน database หรือ route เดิม

WP1 ผ่าน local automated gate แล้วตาม `docs/scopes/WP1-PHASE-GATE-02.md` งานถัดไปคือ
`docs/scopes/WP2-COMPANY-MODULE-ACCESS-01.md` เพื่อย้าย module access ให้เป็น server-owned
Company contract โดยยังไม่เปิดโมดูลหรือ deploy ระบบจริง

WP2 ผ่าน local automated gate แล้วตาม `docs/scopes/WP2-PHASE-GATE-03.md` โดยใช้ plan/profile
JSON controls เดิม จึงไม่ต้อง migration และเพิ่ม server-owned effective access, Company Admin status,
Platform Owner controls กับ audit โดย Takeaway/Hotel ยังคงปิดตาม gate เดิม งานถัดไปคือ
`docs/scopes/WP3-COMPANY-WORKSPACE-PROVISIONING-01.md` เพื่อจัด Company/Brand/Branch workspace
ตาม module access โดยยังไม่ deploy หรือ activate ระบบจริง

WP3 ผ่าน local automated gate แล้วตาม `docs/scopes/WP3-PHASE-GATE-02.md` โดยเพิ่ม Company
Workspace directory, idempotent Restaurant provisioning, deactivate/reactivate พร้อม audit และหน้า
Company Admin `/workspaces` โดยไม่เพิ่ม migration และไม่ให้ client เลือก target database งานถัดไปคือ
`docs/scopes/WP4-SHARED-ERP-REPORTING-CONTRACT-01.md` เพื่อกำหนด ownership และรายงานรวมที่แยก
module/Brand/Branch ก่อนย้าย Central Kitchen หรือเปิดระบบจริง

WP4 ผ่าน local implementation และ isolated migration gate แล้ว โดยเพิ่ม Platform-owned reporting
projection, replay/correction/refund/void audit, Company Admin `/reports/company` และสถานะ freshness แบบ
Shadow/read-only ทั้งหมดไม่เปิด UAT/Production และไม่เปลี่ยน operational system of record หลักฐานอยู่ที่
`docs/architecture/shared-erp-reporting.md` และ `docs/scopes/WP4-PHASE-GATE-02.md`

งานถัดไปคือ `docs/scopes/WP5-CENTRAL-KITCHEN-SHARED-STOCK-01.md` เพื่อให้หลาย Brand ใช้วัตถุดิบ
Company กองเดียวกันได้ โดยแยกสูตร ผลผลิต คำสั่งผลิต ต้นทุน และรายงานตาม Brand ก่อนเริ่มต้อง audit
stock/recipe/production เดิมและผ่าน migration/rollback gate แยก ห้ามเปิดตัดสต๊อกจริงโดยอัตโนมัติ

WP5 ผ่าน local implementation และ automated gate แล้ว โดยเพิ่ม Company-level canonical ingredient,
shared FIFO lot/ledger, demand/production/reversal ที่แยก Brand และหน้า Company Admin `/company-kitchen`
พร้อม dedicated permission ค่า write flag ยังคงปิดและไม่ได้ migrate/deploy UAT/Production หลักฐานอยู่ที่
`docs/architecture/company-shared-kitchen.md` และ `docs/scopes/WP5-PHASE-GATE-02.md`

physical Safari/iPad UAT และ opening-lot mapping ของ WP5 ยังคงพักตามคำสั่ง owner และห้ามเปิด
`COMPANY_KITCHEN_WRITES_ENABLED` หรือรวม stock เดิมจากชื่อ/SKU แบบอัตโนมัติ

WP6 ใหม่ใช้ Scope ID `WP6-SUPPLY-CHAIN-DISTRIBUTION-01` (ไม่ใช่ Phase 6 Takeaway เดิม) เพื่อรวม
Demand จาก Restaurant POS, Takeaway POS และ Retail POS แล้วกระจาย finished goods จาก Brand READY
ไปสาขาผ่าน Transfer/Stock ledger เดิม พร้อม send/receive/reject/return และ reconciliation แยก
Module/Brand/Branch การพัฒนาทำแบบ dark launch, ไม่ query ข้าม database, ไม่ import Chambo จริง
และไม่ deploy/migrate UAT/Production รายละเอียดอยู่ที่
`docs/scopes/WP6-SUPPLY-CHAIN-DISTRIBUTION-01.md`

WP6 ผ่าน local implementation และ automated gate แล้ว โดย normalized Demand ทั้งสาม POS, shipment
ที่ reuse Transfer/Stock ledger เดิม, receive/reject/reverse return, idempotency, tenant/module isolation,
Company Admin `/company-distribution` และ reconciliation แยก Module/Brand/Branch ทำงานครบ
`COMPANY_DISTRIBUTION_WRITES_ENABLED=false` และ `COMPANY_KITCHEN_WRITES_ENABLED=false` ยังปิด,
ไม่มี UAT/Production migration/deployment หลักฐานอยู่ที่ `docs/scopes/WP6-PHASE-GATE-02.md`

WP7 ใช้ Scope ID `WP7-RETAIL-SAAS-ALIGNMENT-01` เพื่อจัด Retail POS เดิมให้ใช้ Company Workspace,
signed staff/device context และ server-owned operational routing พร้อมสร้าง Retail Database boundary,
migration, health, backup/restore แยกแบบ standby ค่า runtime ยังเป็น Legacy และ schema contract version
1 ตั้งใจบล็อก cutover จนกว่า WP8 จะทำ selective data copy, continuous reference projection, parity,
scanner/printer/offline UAT และ owner sign-off รายละเอียดอยู่ที่
`docs/architecture/retail-pos-boundary.md` และไม่มี UAT/Production deployment/activation ใน WP7

WP7 ผ่าน local automated gate แล้ว: backend `312` tests, Retail migration downgrade/re-upgrade,
four-boundary backup/isolated restore, frontend type/build และ Platform browser `18/18` ผ่าน ค่า Retail
runtime ยังเป็น Legacy และ early-cutover ไป schema version 1 ถูกบล็อก หลักฐานอยู่ที่
`docs/scopes/WP7-PHASE-GATE-02.md` งานถัดไปคือ WP8 selective Retail data migration/canary แต่ physical
scanner/printer/offline UAT และ UAT/Production activation ยังคงพัก

WP8 ใช้ Scope ID `WP8-RETAIL-SELECTIVE-MIGRATION-01` และผ่าน local implementation gate แล้ว โดยเพิ่ม
Retail schema contract v2, Platform reference projection ที่ไม่ copy password credential, selective
Company/Brand/Branch migration พร้อม FK ordering/count/digest/replay, Retail shared reporting source และ
isolated sale/refund/void/stock/net-report canary กับ read-only rollback route ค่า runtime จริงยังเป็น
Legacy ไม่มีข้อมูลจริงถูกย้าย และไม่มี UAT/Production deployment/activation รายละเอียดและหลักฐานอยู่ที่
`docs/scopes/WP8-RETAIL-SELECTIVE-MIGRATION-01.md` กับ `docs/scopes/WP8-PHASE-GATE-02.md`

WP8 automated gate: backend full regression `328` tests, focused contracts `40` tests, Retail v2
downgrade/re-upgrade, reference/operational replay parity, isolated canary/rollback และ frontend
type-check/production PWA build (`4,206` modules) ผ่าน

physical Retail scanner/printer/cash drawer/offline UAT, real-data freeze/backup/reconciliation และ owner
sign-off ยังคงพักและเป็นเงื่อนไขบังคับก่อนเปลี่ยน `RETAIL_SERVICE_DATABASE=retail` ในระบบจริง

WP9-A ใช้ Scope ID `WP9-TAX-CONFIGURATION-01` และผ่าน local implementation gate แล้ว โดยเพิ่ม
Tax Profile กลางระดับ Company/Branch, รหัสสาขาภาษีตาม ภ.พ.20, รูปแบบการยื่น ภ.พ.30,
อัตรา Standard/0%/Exempt ตามช่วงเวลา, audit ก่อน–หลัง และหน้า Company Admin `/settings/tax`
ข้อมูลชุดนี้อยู่ใน Shared ERP และใช้ร่วมกันโดย Restaurant, Retail, Takeaway, Purchasing/AP และ e-Tax
โดยไม่ทำสำเนาข้าม operational database

e-Tax อ่านข้อมูลผู้ขายและรหัสสาขาจาก Tax Profile ตามวันที่ขายพร้อม fallback ไปข้อมูลเดิมเพื่อรักษา
legacy flow ส่วน Sales VAT Ledger, Output VAT reconciliation และภาษีซื้อครบวงจรทำต่อใน WP9-B/WP9-C
แล้ว ระบบยังไม่มีการยื่นภาษีจริง หลักฐานอยู่ที่ `docs/scopes/WP9-TAX-CONFIGURATION-01.md`

WP9-B ถึง WP9-H ใช้ Scope ID `WP9-TAX-OPERATIONS-02` และผ่าน local implementation gate แล้ว โดยเพิ่ม
Tax Ledger กลางสำหรับภาษีขาย/ซื้อ, หลักฐานใบกำกับภาษีซื้อ, การจำแนก ภ.ง.ด.3/53, e-Tax reconciliation,
วงจร Review/Close/Reopen พร้อมล็อกงวด, versioned export ที่มี SHA-256 และ readiness gate ก่อนปิดงวด
หน้า Company Admin อยู่ที่ `/tax-center` และเพิ่มสิทธิ์ `accounting.tax.view/manage`

Shared ERP เป็น system of record ของ Tax Operations ส่วน Retail/Takeaway ที่แยกฐานข้อมูลต้องส่ง normalized
tax event ผ่าน idempotent contract ห้าม query ข้าม operational database ระบบยังไม่ส่งแบบให้กรมสรรพากร

วันที่ 16 กันยายน 2026 deploy WP9-A ถึง WP9-H ขึ้น UAT ที่ `https://uat-pos.foodchainservice.com`
ด้วย commit `a08122a`, migration ถึง `p16taxops0018`, image ชุด `wp9-a08122a` และ backup ที่
`/home/behappyaiagent/restaurant-uat-deploy-backups/a08122a`; internal/public health, auto-login,
Tax Settings และ Tax Center dashboard smoke ผ่าน ส่วน Production ไม่ถูกเปลี่ยนแปลง และ physical UAT
กับผู้ทำบัญชียังคงพัก รายละเอียดอยู่ที่ `docs/scopes/WP9-TAX-OPERATIONS-02.md`
