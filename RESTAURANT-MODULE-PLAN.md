# F&B Module — Architecture Plan

**วันที่:** 2026-05-31  
**ครอบคลุม:** ร้านอาหาร + คาเฟ่ + Recipe/ต้นทุน

---

## ข้อตกลงพื้นฐาน

| ประเด็น | การตัดสินใจ |
|--------|------------|
| วัตถุดิบ | ใช้ Product เดิม เพิ่ม type = `raw_material` |
| ตัดสต็อก | ประมาณการรายกะ (ไม่ real-time) |
| Module boundary | แยก router/model ออกจาก pos เดิม |
| Checkout | ยังใช้ SaleOrder เดิม |

---

## Product Types (เพิ่ม field ใน Product เดิม)

```
product_type:
  retail       — สินค้าขายปกติ (เดิม)
  menu_item    — เมนูอาหาร/เครื่องดื่ม
  raw_material — วัตถุดิบ (กาแฟ, นม, แป้ง) — ไม่ขายตรง
```

วัตถุดิบใช้ระบบ Stock และ Purchase Order เดิมได้ทันที
ราคาวัตถุดิบดึงจาก Purchase Order ล่าสุดอัตโนมัติ

---

## Models ใหม่ (F&B Module)

### 1. Recipe + RecipeIngredient

```
recipes
├── id
├── product_id          FK → products (menu_item)
├── branch_id           FK → branches (สูตรต่างสาขาได้)
├── name                ชื่อสูตร เช่น "Latte Standard"
├── yield_qty           ปริมาณที่ได้ต่อครั้ง (default 1)
├── yield_unit          หน่วย เช่น "แก้ว"
├── notes
└── is_active

recipe_ingredients
├── id
├── recipe_id           FK → recipes
├── ingredient_id       FK → products (raw_material)
├── quantity            เช่น 18
└── unit                g / ml / ชิ้น / ช้อนชา
```

**ตัวอย่าง Latte 1 แก้ว:**
| วัตถุดิบ | quantity | unit |
|---------|---------|------|
| กาแฟ Espresso | 18 | g |
| นมสด | 150 | ml |
| น้ำเชื่อม Vanilla | 10 | ml |

---

### 2. Dining Tables + Sessions

```
dining_tables
├── id
├── branch_id
├── name                "A1", "โต๊ะริมหน้าต่าง"
├── capacity            จำนวนที่นั่ง
├── qr_token            UUID สำหรับ public URL
├── table_type          dine_in | bar | takeaway
└── is_active

dining_sessions
├── id
├── table_id            FK → dining_tables
├── branch_id
├── shift_id            FK → cashier_shifts (optional)
├── opened_by           FK → users
├── status              open | bill_requested | closed
├── guest_count
├── opened_at
└── closed_at
```

---

### 3. Dining Orders (ออเดอร์จากโต๊ะ)

```
dining_orders
├── id
├── session_id          FK → dining_sessions
├── branch_id
├── order_number        DO-20260531-001
├── source              qr_self | staff | kiosk
├── status              pending | confirmed | cancelled
├── note
└── created_at

dining_order_items
├── id
├── order_id            FK → dining_orders
├── product_id          FK → products (menu_item)
├── qty
├── unit_price
├── special_request     "ไม่ใส่น้ำตาล", "เพิ่มช็อต"
└── status              pending | cooking | done | served
```

---

### 4. Kitchen Tickets

```
kitchen_tickets
├── id
├── branch_id
├── session_id
├── order_item_id       FK → dining_order_items
├── product_name        denormalized (ครัวอ่านเร็ว)
├── qty
├── special_request
├── station             coffee | food | cold_drink
├── status              pending | cooking | done | served
├── created_at
└── updated_at
```

---

## Ingredient Usage Estimation (รายกะ/รายวัน)

ไม่ตัด stock real-time แต่คำนวณ **ยอดใช้ทฤษฎี** เมื่อ:
- ปิดกะ
- ดูรายงานรายวัน

```
สูตรคำนวณ:
  สำหรับแต่ละวัตถุดิบ:
  theoretical_usage = Σ (qty_sold × recipe_qty)

  ตัวอย่าง:
  ขาย Latte 20 แก้ว, Cappuccino 10 แก้ว
  กาแฟ Espresso = (20 × 18g) + (10 × 18g) = 540g

  เทียบกับ stock ที่นับจริง (Stock Count เดิม)
  variance = theoretical - actual
```

### Ingredient Usage Report แสดง:

| วัตถุดิบ | ใช้จริง (ทฤษฎี) | ราคาต่อหน่วย | ต้นทุนรวม |
|---------|--------------|------------|---------|
| กาแฟ Espresso | 540g | ฿0.85/g | ฿459 |
| นมสด | 4,500ml | ฿0.045/ml | ฿202.50 |
| **รวมต้นทุน** | | | **฿661.50** |

---

## ต้นทุนต่อเมนู (Cost per Menu Item)

```
cost_per_item = Σ (ingredient_qty × latest_purchase_price_per_unit)

ตัวอย่าง Latte:
  กาแฟ 18g × ฿0.85 = ฿15.30
  นม 150ml × ฿0.045 = ฿6.75
  น้ำเชื่อม 10ml × ฿0.12 = ฿1.20
  ─────────────────────────
  ต้นทุน = ฿23.25
  ราคาขาย = ฿85.00
  gross margin = 72.6%
```

ราคาวัตถุดิบดึงจาก Purchase Order ล่าสุดของวัตถุดิบนั้น

---

## Frontend Pages

### 0. `/restaurant/orders` — Restaurant Paid-First WAP (Staff)

Dedicated branch-staff app for `ระบบร้านอาหาร`.

**Phase 1: WAP รับออเดอร์**
- [x] Dedicated `/restaurant/orders` URL outside the main ERP sidebar
- [x] Hidden app chrome/header for more menu space
- [x] Hamburger menu for รับออเดอร์ / ครัว / จอคิว / ออกจากระบบ
- [x] Branch login context and default branch selection kept behind the dedicated shell
- [x] Branch menu loaded from active `menu_item` products
- [x] Menu cards with inline price, quantity, and +/- controls
- [x] Summary hidden until staff taps `สรุปออเดอร์`
- [x] Summary review page with quantity edit controls
- [x] Summary shows each configured menu item and its quantity
- [x] Two paid-first payment buttons: cash and PromptPay
- [x] Queue issued after payment button is pressed
- [x] Customer slip prints before kitchen slip
- [x] Kitchen slip action creates/sends kitchen tickets after customer slip
- [x] Queue/result screen shows ordered items before printing

**Next phase: ปิดกะ / Stock / สั่งซื้อส่วนกลาง**
- [ ] Close-shift screen for Restaurant branch
- [ ] Calculate theoretical stock usage from WAP paid orders
- [ ] Branch staff stock count at shift close
- [ ] Variance display: expected usage vs counted stock
- [ ] Suggested purchase/request quantities after close shift
- [ ] Branch can edit requested quantities before submit
- [ ] Send purchase/request to central office
- [ ] Central admin view for branch requests

### 1. `/restaurant/tables` — Table Map (Cashier)
- Grid โต๊ะ แสดงสถานะ (ว่าง / มีลูกค้า / เรียกบิล)
- คลิกโต๊ะ → เปิด session / ดูออเดอร์ / รวมบิล
- แสดง QR code ต่อโต๊ะ (print ได้)

### 2. `/menu/:qr_token` — Customer Menu (Public, no login)
- หน้าเมนูสำหรับลูกค้า (mobile-first)
- เลือกเมนู → ใส่ special request → ส่งออเดอร์
- ดูสถานะออเดอร์ของตัวเอง
- ปุ่ม "เรียกบิล"

#### Customer Mobile Ordering Checklist

**Dine-in `/menu/:qr_token`**
- [x] โหลดเมนูจาก QR โต๊ะแบบ public
- [x] แสดงชื่อสาขา / ชื่อโต๊ะ / เลขคิว
- [x] เลือกหมวดเมนูแบบ horizontal tabs
- [x] เพิ่ม/ลดจำนวนจากรายการเมนู
- [x] เพิ่มหมายเหตุรายเมนูและหมายเหตุรวม
- [x] ส่งออเดอร์เข้า dining session
- [x] แสดงสถานะรายการอาหารและเรียกบิล
- [x] แยก shared mobile menu components ใช้ร่วมกับ Quick Service
- [x] เพิ่ม search menu บน mobile
- [x] เพิ่ม item detail/options สำหรับ modifier เช่น หวานน้อย เพิ่มช็อต
- [x] เพิ่ม confirmation/empty state ที่ polish กว่านี้
- [x] จดจำตะกร้าตาม QR token เพื่อกันรายการหายเมื่อ refresh
- [x] แสดงสถานะออเดอร์เดิมหลัง refresh และล็อกสั่งเพิ่มเมื่อเรียกบิลแล้ว
- [x] แสดง backend error บนหน้าลูกค้าแบบอ่านเข้าใจ
- [x] ปรับ mobile polish สำหรับจอแคบ ปุ่มล่าง safe area และ loading state ระหว่างโหลดสถานะ

**Quick Service `/order/:qr_token`**
- [x] โหลดเมนูจาก QR ร้านแบบ public
- [x] ส่งออเดอร์และออกเลขคิว
- [x] แสดงสถานะคิวสำหรับรับเอง
- [x] ใช้ shared mobile menu components ชุดเดียวกับ dine-in
- [x] เพิ่ม customer phone optional สำหรับติดตามคิว
- [x] ปรับ pickup status ให้เห็นเด่นบนมือถือและจอ pickup
- [x] จดจำตะกร้าตาม QR token และกู้สถานะคิวเดิมหลัง refresh
- [x] กัน localStorage เสียทำให้หน้า public order พัง
- [x] แสดง backend error บนหน้าลูกค้าแบบอ่านเข้าใจ
- [x] ปรับ mobile polish สำหรับจอแคบ ปุ่มล่าง safe area และ loading state ระหว่างโหลดคิว

**Staff Displays**
- [x] ปรับ Kitchen Display ให้เรียงรายการเก่าก่อนและแสดงงานเกิน 10 นาที
- [x] ปรับ Kitchen Display ให้กรองทุกช่องทาง / โต๊ะ / รับเอง และแสดง source badge ต่อ ticket
- [x] ปรับ Kitchen Display ให้ปุ่มสถานะใหญ่ขึ้น แสดงหมายเหตุเด่น และมี manual refresh/error state
- [x] ปรับ Pickup Display ให้คิวแรกเด่นและคิวอื่นอ่านง่าย
- [x] ปรับ Pickup Display ให้แสดงเฉพาะ Quick Service พร้อม item count, ready time, loading/error state
- [x] เพิ่ม Pickup Display sound toggle, last updated และ highlight คิวรอนาน
- [x] ปรับ Table Map ให้เห็นจำนวนโต๊ะว่าง / มีลูกค้า / เรียกบิล
- [x] แก้ flow เรียกบิลให้ table status และ active session แสดงใน Table Map ถูกต้อง
- [x] แก้การเพิ่มโต๊ะให้มี branch context จริงและแสดง error เมื่อสร้างไม่สำเร็จ
- [x] เพิ่มการแก้ไขโต๊ะ คัดลอกลิงก์ QR และปิดใช้งานโต๊ะจาก Table Map
- [x] เพิ่ม dialog เปิดโต๊ะพร้อมจำนวนลูกค้า ชื่อลูกค้า และเบอร์โทร
- [x] กันการเปลี่ยนโต๊ะเป็นว่างเมื่อยังมี session เปิดอยู่
- [x] ปรับ QR preview ให้มีลิงก์ คัดลอกลิงก์ และ print เฉพาะการ์ด QR
- [x] เพิ่ม badge ออเดอร์ใหม่จาก QR / ค้างครัว / พร้อมเสิร์ฟ บน Table Map

**Order Lifecycle**
- [x] ปรับ Session Detail ให้เห็น customer info, source, order number และสถานะรายการชัดขึ้น
- [x] ปรับ Session Detail ให้มี board แยก pending / cooking / done / served พร้อม action เสิร์ฟแล้ว/ยกเลิก
- [x] เพิ่ม filter หน้า Orders แยก โต๊ะ / Quick Service / สถานะ active / เรียกบิล / ปิดแล้ว
- [x] ปรับ Checkout ให้ส่ง reference no สำหรับบัตร/โอนและ refresh queue/table/order หลังชำระ
- [x] เพิ่ม warning เมื่อ checkout ขณะที่ครัวยังมีรายการ pending/cooking
- [x] ปรับ checkout warning ให้มีปุ่มกลับไปดู Session Detail หรือ Kitchen Display
- [x] เพิ่ม cancel order/item flow พร้อมเหตุผลและ sync ticket ครัว
- [x] เพิ่ม receipt detail สำหรับ F&B ให้แสดงโต๊ะ/คิว/source/customer/payment ครบ
- [x] ปรับใบเสร็จร้านอาหารให้มี thermal print layout และแสดง payment reference
- [x] เพิ่ม guard สถานะครัวและ served workflow จาก Session Detail/Kitchen Display
- [x] เพิ่ม smoke test ครอบคลุม Quick Service และ Dine-in E2E จนถึง pickup/served/checkout
- [x] เพิ่ม Quick Service checkout จากหน้า Orders เมื่อคิวพร้อมรับแล้ว พร้อมเลือกวิธีชำระและ reference

### 3. `/restaurant/kitchen` — Kitchen Display
- แสดง ticket แบบ Kanban: pending | cooking | done
- ลาก / กดเปลี่ยนสถานะ
- Auto-refresh ทุก 5 วินาที พร้อม manual refresh
- กรองตามช่องทาง โต๊ะ / Quick Service และสถานีครัว

### 4. `/restaurant/recipes` — Recipe Management
- สร้าง/แก้ไขสูตรต่อเมนู
- ดูต้นทุนต่อแก้ว/จาน
- ดู gross margin
- [x] เพิ่ม UI แก้ไขสูตรเดิม พร้อมเปลี่ยน yield, notes และรายการวัตถุดิบ
- [x] เพิ่มการสร้างวัตถุดิบใหม่จากหน้าสูตรโดยใช้สิทธิ์ `fb.recipe.manage`
- [x] เพิ่ม demo raw materials และ sample recipes สำหรับทดสอบต้นทุน

### Demo F&B Menu Seed
- [x] เพิ่ม script `python -m app.utils.seed_fnb_demo` สำหรับสร้างเมนูทดสอบ 4 หมวด / 12 รายการ
- [x] Seed raw materials และ sample recipes สำหรับ recipe/cost testing
- ใช้ซ้ำได้ผ่าน backend container: `docker compose exec backend python -m app.utils.seed_fnb_demo`

### Test Coverage / UAT
- [x] เพิ่ม smoke script `scripts/fnb-smoke.sh` สำหรับ flow seed menu → quick service order → kitchen ticket → customer status
- [x] เพิ่ม UAT checklist ร้านอาหารใน `UAT-RESTAURANT.md`
- [x] เพิ่มคู่มือปฏิบัติงานร้านใน `RESTAURANT-OPERATIONS-GUIDE.md`

### Restaurant Permissions
- [x] แยกสิทธิ์จัดการโต๊ะ/session เป็น `fb.table.manage`
- [x] แยกสิทธิ์สั่งอาหาร/เรียกบิล/checkout/cancel เป็น `fb.order.create`
- [x] แยกสิทธิ์ครัวเป็น `fb.kitchen.manage`
- [x] แยกสิทธิ์สูตรและวัตถุดิบเป็น `fb.recipe.manage`
- [x] แยกสิทธิ์ตั้งค่า QR/notification เป็น `fb.settings.manage`

### 5. `/restaurant/reports/ingredients` — Ingredient Report
- ยอดใช้วัตถุดิบรายกะ/รายวัน
- เทียบ theoretical vs stock count จริง
- Export CSV

---

## API Routes

```
# Staff (require auth)
GET    /api/v1/restaurant/tables
POST   /api/v1/restaurant/tables
PATCH  /api/v1/restaurant/tables/{id}

POST   /api/v1/restaurant/sessions           เปิดโต๊ะ
PATCH  /api/v1/restaurant/sessions/{id}      เปลี่ยนสถานะ
POST   /api/v1/restaurant/sessions/{id}/checkout  รวมบิล → SaleOrder

GET    /api/v1/restaurant/kitchen            ดู tickets (polling)
PATCH  /api/v1/restaurant/kitchen/{id}       เปลี่ยนสถานะ

GET    /api/v1/restaurant/recipes
POST   /api/v1/restaurant/recipes
PATCH  /api/v1/restaurant/recipes/{id}
POST   /api/v1/restaurant/raw-materials

GET    /api/v1/restaurant/reports/ingredients

# Public (no auth — ลูกค้าสแกน QR)
GET    /api/public/dine/{qr_token}           ดูเมนู + session info
POST   /api/public/dine/{qr_token}/orders    สั่งอาหาร
GET    /api/public/dine/{qr_token}/orders    ดูสถานะออเดอร์ตัวเอง
POST   /api/public/dine/{qr_token}/bill      เรียกบิล
```

---

## ลำดับการ Implement

| Phase | งาน | เวลา |
|-------|-----|------|
| **1** | Product type field + Migration | ครึ่งวัน |
| **2** | Recipe models + CRUD API | 1 วัน |
| **3** | Recipe Management UI + cost calculator | 1 วัน |
| **4** | Dining tables + sessions API | 1 วัน |
| **5** | Table Map UI (cashier) | 1 วัน |
| **6** | Customer Menu Page (public QR) | 1 วัน |
| **7** | Kitchen Display | ครึ่งวัน |
| **8** | Session → SaleOrder checkout | 1 วัน |
| **9** | Ingredient Usage Report | ครึ่งวัน |
| **รวม** | | **~8 วัน** |

---

## สิ่งที่ไม่ต้องสร้างใหม่ (ใช้ของเดิม)

- Product catalog → เพิ่ม type เท่านั้น
- Stock system → วัตถุดิบอยู่ใน StockBalance เดิม
- Purchase Order → ดึงราคาวัตถุดิบอัตโนมัติ
- SaleOrder + Payment → checkout ใช้ flow เดิม
- eTax / Receipt → ทำงานได้ทันที
- CRM / Loyalty → ทำงานได้ทันที
- Reports → เพิ่ม filter source=restaurant
- Auth / Branch / Permission → ใช้เดิม
