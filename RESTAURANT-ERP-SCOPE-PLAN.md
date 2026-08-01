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

- [ ] Tablet ครัวเข้าได้โดยไม่ใช้บัญชี Company Owner
- [ ] Tablet ที่ถูก revoke ใช้งานต่อไม่ได้
- [ ] Counter, Kitchen และ Pickup เห็นเฉพาะ Branch ที่จับคู่
- [ ] ทดสอบ offline/reconnect ขั้นพื้นฐานโดยออเดอร์ไม่ซ้ำ

ไม่รวม: Native mobile app และ MDM

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

- [ ] Brand Manager เห็นข้อมูลรวมเฉพาะแบรนด์
- [ ] Branch Manager เห็นเฉพาะสาขาที่ได้รับมอบหมาย
- [ ] ต้นทุนเมนูคำนวณจากวัตถุดิบและหน่วยนับที่ตรวจสอบได้
- [ ] การขายทำให้เกิด stock/payment/accounting handoff เพียงครั้งเดียว
- [ ] Restaurant operational data ไม่มี SQL foreign key ไป Retail/Takeaway Database
- [ ] รายงานรวมเท่ากับผลรวมรายการต้นทาง

ไม่รวม: AI forecast, advanced CRM และ franchise royalty

### Phase 5 — Platform Onboarding และ Go-live

ขอบเขต:

- Platform console ขั้นต่ำสำหรับสร้าง/ระงับ Company
- Onboarding checklist: Company → Brand → Branch → Menu → Payment → Staff → Device
- Feature flags และ plan limit แบบ manual
- Backup, restore, monitoring, incident และ tenant export
- UAT และ production security review

Acceptance Criteria:

- [ ] สร้างร้านลูกค้าใหม่โดยไม่แก้ source code หรือ SQL ด้วยมือ
- [ ] ปิด Company แล้วทุก user/device ของ tenant เข้าไม่ได้
- [ ] Backup/restore tenant test ผ่าน
- [ ] UAT ตั้งแต่ QR order จนถึง ERP report ผ่าน
- [ ] Production checklist และ owner sign-off ครบ

ไม่รวม: ระบบเก็บเงิน subscription อัตโนมัติ

### Restaurant Completion Gate — ต้องผ่านก่อนเริ่มระบบอื่น

Restaurant ถือว่าเสร็จสำหรับเริ่ม Phase 6 เมื่อครบทั้งหมด:

- [ ] Phase 0–5 ผ่าน Acceptance Criteria
- [ ] ครัวป่า ปลาเขื่อนผ่าน UAT แบบ dine-in และรับกลับ
- [ ] Role/Scope อย่างน้อย Owner, Manager, Cashier และ Kitchen ผ่าน security test
- [ ] Restaurant ERP report กระทบยอดกับ order/payment/stock ได้
- [ ] Backup/restore และ rollback ผ่าน
- [ ] Retail POS regression suite ผ่าน
- [ ] Platform Owner ลงนามอนุมัติ Restaurant completion

หาก Gate ข้อใดไม่ผ่าน ห้ามเริ่ม Phase 6 แม้งาน Takeaway จะดูเหมือนใช้เวลาไม่นาน

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

- [ ] สร้าง Takeaway Company/Brand/Branch ได้โดยไม่แก้ source code หรือ SQL
- [ ] Takeaway branch เปิด Restaurant/Retail operational API ไม่ได้
- [ ] QR → Order → Kitchen → Pickup → Bill → Payment → ERP report ผ่าน
- [ ] Takeaway order/stock/payment records อยู่ใน Takeaway Database เท่านั้น
- [ ] Takeaway Database backup/restore และ migration ทำงานแยกจาก Restaurant/Retail
- [ ] ข้อมูล Takeaway แยก Company/Brand/Branch และผ่าน cross-tenant test
- [ ] Restaurant เดิมและ Retail POS regression ผ่านหลังเพิ่ม Takeaway system

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
