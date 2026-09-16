# WP16 — Chambo Full Migration Discovery และ Gap Matrix

วันที่ตรวจ: 2026-09-16

สถานะ: **completed_discovery — พร้อมเริ่ม WP17; ยังไม่มีการย้ายข้อมูลจริงหรือเปิด Production**

## 1. เป้าหมาย

ตรวจ Chambo ปัจจุบันแบบ read-only แล้วกำหนดรายการงานสำหรับนำความสามารถที่จำเป็นทั้งหมดมาเป็น
Foodchainservice Takeaway โดยไม่คัดลอก secret, production configuration, credential หรือความผูกกับ
Restaurant database มาปะปนกับ Takeaway database

คำว่า “เอา Chambo มาทั้งหมด” ในแผนนี้หมายถึง:

- นำ workflow ธุรกิจ หน้าปฏิบัติงาน กฎข้อมูล งาน offline อุปกรณ์ และรายงานที่ยังใช้งานได้มาให้ครบ
- ย้ายข้อมูลจริงเฉพาะ snapshot ที่ owner อนุมัติ ผ่าน versioned import และ reconciliation
- เปลี่ยนชื่อ/branding/route/permission ให้เป็น Foodchainservice Takeaway
- ใช้ Platform, Shared ERP, Central Kitchen และ Supply Chain ที่มีอยู่แทนการสร้างระบบซ้ำ
- ไม่ย้าย password, token, session, private key, `.env`, production database URL หรือ hardcoded Chambo identity
- ไม่นำ Dining Table/Dining Session ของ Restaurant POS เข้ามาใน Takeaway

## 2. Baseline ที่ตรวจ

| ส่วน | Path / baseline | ผลตรวจ |
| --- | --- | --- |
| Chambo source | `/Users/user/Projects/erp-pos-run` @ `24e9300bde16c5be72f9eb56bad74fb59401bd06` | อ่านอย่างเดียว, branch `main`, clean |
| Foodchainservice target | `/Users/user/Projects/restaurant` @ `537e05caf46d331a215ad6ca2604af6c2c2a069d` | Takeaway UAT เปิดอยู่; Production ยัง blocked |
| Baseline เดิม | Chambo `15a1de1` | มี change เพิ่มเรื่องแยก central order ตามสาขาใน baseline ใหม่ |

Chambo source ไม่ถูกแก้ไฟล์ ไม่เปลี่ยน remote และไม่ถูก push ระหว่าง WP16

## 3. สิ่งที่มีอยู่แล้วใน Foodchainservice

Takeaway ไม่ได้เริ่มจากศูนย์ ปัจจุบันมีฐานต่อไปนี้แล้ว:

- Takeaway database แยก, reference projection และ permission namespace ของตัวเอง
- 32 Takeaway model classes และ 43 HTTP routes
- Catalog, branch availability, shift, paid-first sale, payment, receipt snapshot และ refund
- Customer QR ordering, Kitchen ticket, Pickup token/status และการส่งมอบ
- Central order/round, production batch, stock ledger, transfer และ credit ledger รุ่นพื้นฐาน
- Shared ERP outbox, acknowledge และ reconciliation
- Chambo import contract, validator, synthetic import, historical archive และ opening balance
- หน้า Dashboard, Counter, Kitchen, Pickup, Central, Production, Stock, Transfer, Credit, Report,
  Import และ ERP แบบ web/PWA
- UAT แยกฐานข้อมูล Takeaway และมีข้อมูลจำลองสำหรับจัด UI
- automated Takeaway tests 5 ไฟล์ รวมประมาณ 1,126 บรรทัด

Repository เป้าหมายยังมี workflow Chambo ที่เคย generalize เป็น Restaurant shared operations แล้ว เช่น
หน้าปิดกะ สั่งครัวกลาง ผลิต สต๊อก เครดิต สูตร cutover และรายงาน รวมกว่า 7,000 บรรทัด จุดนี้ใช้เป็น
reference/องค์ประกอบร่วมได้ แต่ห้ามให้ Takeaway เรียก Restaurant operational tables โดยตรง

## 4. Inventory จาก Chambo ปัจจุบัน

### 4.1 หน้าร้าน

- ขายแบบ paid-first, เลขคิว, สลิปลูกค้าและสลิปร้าน
- เก็บ menu snapshot ในเครื่อง, สร้างเลขคิว offline และ sync ด้วย client order ID
- pending/syncing/needs-review/retry และรองรับ lost acknowledgement
- ปิดกะหลายรอบ, สรุปยอดขายตามพนักงาน และประวัติปิดกะ
- stock ประจำวัน, รับ/ใช้/เสีย/คงเหลือ และปรับยอด
- ใบสั่งประจำวัน, สั่งเพิ่ม, ขอสินค้านอก catalog และยืนยันรับสินค้า
- แจ้งเติมเครดิตด้วย QR/สลิปและดูสถานะคำขอ
- Staff request ระดับร้านและสาขา

### 4.2 ส่วนกลาง

- ดูใบสั่งแยกสาขา, อนุมัติ, แพ็ก, ส่ง, ยกเลิก และแก้รายการที่ยังไม่ map
- สรุปยอดผลิตและวัตถุดิบจากใบสั่ง
- Replenishment policy, safety stock, pack size, lead time และ minimum order
- Production batch: plan/start/complete/cancel, input/output และ READY stock
- RAW/READY/STORE/TRANSIT stock, movement, transfer และ discrepancy ตอนรับ
- สูตรขาย/สูตรผลิต/สูตรซ้อน, version, yield, loss และ unit conversion
- เครดิตแฟรนไชส์, ledger, top-up request approve/reject/refund และ QR บริษัท
- Stock Control Tower, รายงานสาขา/พนักงาน/ปิดกะ/ผลิต/เครดิต/ส่งรับ/ต้นทุนสูตร
- Stock separation cutover แบบ preview/confirm/history

### 4.3 App, offline และอุปกรณ์

- Capacitor Android app `com.chambo.pos`
- Bluetooth ESC/POS printer plugin, permission, paired device, raster image, feed และ cut paper
- printer settings/test page และ customer/merchant receipt flow
- Android release manifest, version check และ APK download endpoint
- IndexedDB/Dexie menu snapshot, outbox, queue counter และ retry workflow

Source UI ที่เกี่ยวข้องโดยตรงมีประมาณ 9,191 บรรทัด รวม 12 หน้าปฏิบัติงาน,
offline library, printer settings และ app update UI จึงต้องย้ายเป็นช่วง ไม่ควร copy ครั้งเดียวทั้งก้อน

## 5. Gap Matrix

คำสถานะ:

- **พร้อม** — bounded context ของ Takeaway ทำงานหลักครบแล้ว
- **บางส่วน** — มี model/API หรือ UI แล้ว แต่ยังไม่ครบ workflow Chambo
- **ยังขาด** — ยังไม่มี Takeaway implementation ที่ใช้งานจริง
- **ใช้ของกลาง** — ให้ใช้ Platform/Shared ERP/Supply Chain โดยไม่สร้างซ้ำ

| กลุ่ม | Chambo capability | Takeaway ปัจจุบัน | Gap ที่ต้องปิด | งาน |
| --- | --- | --- | --- | --- |
| Tenant | Company/Brand/Branch | พร้อม | เพิ่ม route เข้า workspace ตามบทบาทและ brand theme | WP17 |
| Counter | paid-first, queue, cash/payment | พร้อมด้าน service; UI ยังย่อ | ทำ counter UX ให้เทียบ Chambo, resume/retry และ receipt action | WP18 |
| Offline | menu cache, local queue, outbox, retry | บางส่วน: API รองรับ offline แต่ Counter ไม่มี Takeaway IndexedDB outbox | สร้าง Takeaway offline adapter แยกจาก Restaurant และ lost-ack recovery | WP18 |
| Receipt | customer/merchant slip และพิมพ์ซ้ำ | บางส่วน: มี receipt snapshot; Counter ยังไม่มี flow พิมพ์ครบ | template, reprint audit, customer/merchant ordering และ fallback web print | WP18/WP20 |
| Shift | เปิด/ปิดหลายรอบและสรุปแคชเชียร์ | บางส่วน: API เปิด/ปิดมี แต่หน้าใช้งานยังไม่ครบ | close summary, counted cash, variance, history และ cashier report | WP18 |
| Store stock | stock daily/adjust/waste | บางส่วน: ledger/movement มี | หน้า daily movement, reason, approval และ stock warning | WP18 |
| Store ordering | regular/extra/unlisted/receive | บางส่วน: schema รองรับชนิดใบสั่งและสถานะพื้นฐาน | idempotent daily order, extra reason, unlisted resolve, partial receive/discrepancy | WP18/WP19 |
| Public QR | menu/order/payment/pickup | พร้อมด้าน service และ basic UI | polish, expiry/revoke UX, receipt/status field test | WP18/WP24 |
| KDS/Pickup | preparing/ready/picked-up | พร้อมด้าน service และ basic UI | station filter, sound/full-screen, concurrency และ operator UX | WP18/WP24 |
| Central orders | approve/pack/ship/cancel แยกสาขา | บางส่วน: create/list/status รวมอยู่หน้าเดียว | workspace แยกสาขา, item resolution, pack qty, audit และ transition guard | WP19 |
| Replenishment | forecast/safety/pack/lead/minimum | ยังขาด API/UI แม้มี model/import | service, settings, suggestion และ daily-order generator | WP19 |
| Recipes | recipe/version/yield/loss/UOM/nesting | ยังขาด API/UI แม้มี model/import | recipe service, loop/UOM validation, cost และ effective version | WP19 |
| Production | plan/start/complete/cancel/waste | บางส่วน: create/complete พื้นฐาน | summary จาก demand, start/cancel, waste/yield, recipe trace และ replay guard | WP19 |
| Stock | RAW/READY/STORE/TRANSIT ledger | พร้อมด้านโครงสร้าง; UI พื้นฐาน | dashboard, movement history, lot/cost UX และ shared-stock link | WP19 |
| Transfer | ship/receive/discrepancy | บางส่วน: shipped/received/cancelled | packed/shipped qty, partial receive, discrepancy resolution และ return | WP19 |
| Credit | account/ledger | บางส่วน | QR config, slip upload, pending request, approve/reject, reserve/capture/release/refund | WP19 |
| Reports | operational control tower | บางส่วน: sales summary เท่านั้น | branch/cashier/shift/order/production/credit/transfer/recipe-cost reports | WP19 |
| Staff | store/central staff assignment | ใช้ของกลาง | เพิ่ม shortcut/preset ใน Takeaway; ownership อยู่ Platform Identity | WP17/WP22 |
| Android shell | native app | บางส่วน: มี Android shell แต่ identity ยังเป็น Restaurant POS | สร้าง Foodchainservice Takeaway app identity/flavor และ release pipeline | WP20 |
| Bluetooth | paired ESC/POS print | ยังขาดใน target app | port plugin แบบ reviewed, permission/settings/test/error recovery | WP20 |
| App update | version/APK update | ยังขาด | signed release manifest, checksum, update prompt และ rollback version | WP20 |
| Real data | master/opening/history | บางส่วน: contract + synthetic import | exporter, signed snapshot, media scan, actual dry-run และ reconciliation | WP21/WP25 |
| Cutover tool | preview/execute/history | ยังขาดใน Takeaway | approval gate, immutable run, rollback link และ operator evidence | WP21/WP26 |
| Security | tenant/permission/device boundary | พร้อมพื้นฐาน | permission matrix ทุกหน้า, upload hardening, native secret scan และ abuse tests | WP22 |
| ERP/Tax | versioned operational events | พร้อม | เพิ่ม event ของ workflow ใหม่และ parity report | WP19/WP23 |
| Shared kitchen/stock | วัตถุดิบร่วมหลายแบรนด์ | ใช้ของกลาง | เชื่อมผ่าน versioned contract; ห้าม SQL join ข้าม database | WP19/WP22 |
| Delivery/aggregator | marketplace/rider | ไม่มี complete Chambo domain | ไม่ถือเป็น Chambo migration; ขอ Scope Change แยกหากต้องการ | นอก WP16–26 |

## 6. Route และหน้าจอเป้าหมาย

รักษา URL สาธารณะปัจจุบันไว้ และจัดหน้าพนักงานให้อยู่ใต้ Takeaway shell:

| Chambo เดิม | Foodchainservice เป้าหมาย |
| --- | --- |
| `/store/:brandSlug/orders` | `/takeaway/store/orders` |
| `/store/:brandSlug/close-shift` | `/takeaway/store/shifts` |
| `/store/:brandSlug/stock` | `/takeaway/store/stock` |
| `/store/:brandSlug/replenishment-orders` | `/takeaway/store/central-orders` |
| `/store/:brandSlug/credits` | `/takeaway/store/credits` |
| `/store/:brandSlug/staff` | `/takeaway/store/staff` |
| `/central/:brandSlug/orders` | `/takeaway/central/orders` |
| `/central/:brandSlug/production` | `/takeaway/central/production` |
| `/central/:brandSlug/stock` | `/takeaway/central/stock` |
| `/central/:brandSlug/credits` | `/takeaway/central/credits` |
| `/central/:brandSlug/reports` | `/takeaway/central/reports` |
| `/central/:brandSlug/recipes` | `/takeaway/central/recipes` |
| `/central/:brandSlug/cutover` | `/takeaway/admin/cutover` |
| `/central/:brandSlug/staff` | `/takeaway/central/staff` |

Brand/Branch มาจาก signed workspace context ไม่รับค่าจาก URL แล้วนำไปเลือก database เอง
route ปัจจุบัน `/takeaway/counter`, `/takeaway/kitchen`, `/takeaway/pickup` และ public QR ยังคงรองรับ

## 7. แผนส่งมอบ WP17–WP26

| WP | งาน | ผลลัพธ์ที่ต้องได้ก่อนจบ |
| --- | --- | --- |
| WP17 | Takeaway IA, shell, role workspace และ route migration | หน้าร้าน/ส่วนกลาง/ผู้ดูแลแยกชัด, permission/brand context ถูกต้อง, legacy link มี redirect |
| WP18 | Store operation parity | counter, offline, receipt, shift, stock, regular/extra/unlisted order, QR/KDS/Pickup ใช้ได้ครบ |
| WP19 | Central operation parity | recipe, replenishment, central order, production, stock, transfer, credit, reports และ ERP events ครบ |
| WP20 | Android/device parity | Takeaway Android flavor, Bluetooth printer, app update และ signed build evidence |
| WP21 | Real migration tooling | read-only exporter, signed bundle, importer, cutover preview และ reconciliation report |
| WP22 | Security/boundary acceptance | role/tenant/upload/device/idempotency/security tests ผ่าน ไม่มี secret หรือ cross-database access |
| WP23 | Simulation/regression | automated journey ทุกบทบาท, offline/lost-ack/replay/rollback และ 3-system regression ผ่าน |
| WP24 | Physical UAT | Android/iPad, touch, camera, printer, network interruption, KDS/Pickup และ operator handoff ผ่าน |
| WP25 | Approved-data dry run | count/hash/amount/opening balance ตรง, unresolved = 0 หรือมี owner waiver |
| WP26 | Canary/cutover | final backup, one-branch canary, monitoring, rollback drill, owner go/no-go และ production activation |

## 8. ลำดับเริ่ม WP17

1. แยก Takeaway navigation เป็น Store / Central / Admin โดยไม่เปลี่ยน public URL
2. สร้าง route map และ permission matrix จาก signed business context
3. แยกหน้า operations เดียวให้เป็นหน้าเฉพาะงาน เพื่อพร้อมรับ workflow Chambo
4. เพิ่ม redirect จาก route ชั่วคราวและคง deep link ที่ใช้อยู่
5. ใส่ UI fixture จาก UAT dataset และทดสอบ type-check/build/browser navigation

WP17 ยังไม่เพิ่ม migration, ไม่ import Chambo จริง, ไม่เปลี่ยน UAT/Production feature flag และไม่แก้
repository `/Users/user/Projects/erp-pos-run`

## 9. Acceptance Criteria ของ WP16

- [x] Pin source/target commit ที่ตรวจได้
- [x] ตรวจ Store, Central, Recipe, Production, Stock, Credit, Reports, Offline และ Android
- [x] แยกสิ่งที่มีแล้ว/มีบางส่วน/ยังขาด/ใช้ของกลาง
- [x] กำหนด route เป้าหมายโดยไม่ให้ client เลือก database
- [x] ระบุขอบเขตการย้ายข้อมูลและสิ่งที่ห้ามย้าย
- [x] กำหนด WP17–WP26 พร้อม exit outcome
- [x] Chambo source ยัง clean และไม่ถูกแก้ไข
- [x] Production ยังไม่ถูกเปลี่ยนแปลง

คำสั่งงานถัดไป: **เริ่ม WP17 — Takeaway Information Architecture และ Role Workspaces**
