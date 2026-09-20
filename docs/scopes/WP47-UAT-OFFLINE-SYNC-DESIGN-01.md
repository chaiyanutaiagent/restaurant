# WP47 — UAT Offline/Sync Design Contract

วันที่: `2026-09-20`
สถานะ: **Design approved for implementation planning — feature remains disabled**
ขอบเขต: Restaurant POS, Retail POS และ Takeaway POS บน Desktop/iPad; UAT only

## 1. เป้าหมายและเส้นแบ่งอำนาจ

Offline Mode มีไว้ให้หน้าร้านรักษางานขายพื้นฐานระหว่างเครือข่ายขัดข้อง โดย Local Device เก็บเพียง
intent และ snapshot สำหรับแสดงผลเท่านั้น Server ยังคงเป็น authority ของราคา ภาษี สิทธิ์อนุมัติ
ยอดที่คืนได้ สต๊อก loyalty เอกสาร และสถานะทางบัญชีเสมอ

รอบนี้ **ยังไม่เปิด Offline Mode จริง** ทั้งใน UAT และ Production ค่าเริ่มต้นของ feature flag ต้องเป็น
`false` และต้องไม่มี fallback อัตโนมัติเมื่อ API ล้มเหลว

## 2. Capability matrix

| Action | Offline | เหตุผล/เงื่อนไข |
| --- | --- | --- |
| เปิดเมนู/สินค้า/ราคา cache | read-only | ต้องแสดง `Offline · ข้อมูลอาจไม่ล่าสุด` และเวลา snapshot |
| สร้างตะกร้า/แก้จำนวน/โน้ต | อนุญาต | local intent เท่านั้น ยังไม่ใช่ Sale |
| พักบิล | อนุญาตแบบ local shadow | ห้ามสร้าง Payment/Stock/Tax; sync แล้วต้อง reprice/revalidate |
| รับเงินสดและสร้าง pending sale | อนุญาตแบบจำกัดในเฟสเปิดจริง | ต้องมี paired device, open shift, offline authorization ที่ไม่หมดอายุ, THB เท่านั้น และไม่ใช้ราคา stale เกิน TTL |
| QR/PromptPay, บัตร, โอน, provider payment | ห้าม | ต้องยืนยัน provider/settlement กับ Server |
| Price Override/ส่วนลดที่ต้องอนุมัติ | ห้าม | approval token ห้าม cache และห้าม self-approve |
| Refund/Void/Cancellation หลังครัว | ห้าม | ต้อง lock ยอดเดิม, ตรวจสถานะ provider, approval และ audit ที่ Server |
| ออก Tax Invoice/Credit Note/เลขเอกสารจริง | ห้าม | ป้องกันเลขซ้ำและเอกสารภาษีผิดงวด |
| ตัด/คืนสต๊อก, Loyalty, ERP/บัญชี | ห้ามทำที่ client | เกิดหลัง Server accept เท่านั้น |
| ปิดกะ/ส่งมอบกะ | ห้ามเมื่อ queue ไม่ว่างหรือ Server ติดต่อไม่ได้ | ต้อง reconcile เงินสดและ pending/unknown ก่อน |

Retail ใช้กฎเดียวกันสำหรับ barcode sale; Takeaway ใช้ local queue number ได้ แต่เลขรับสินค้าฝั่ง Server,
KDS, stock และ ERP handoff ต้องรอ Server accept

## 3. Local authority และข้อมูลที่ห้ามเก็บ

Local store เก็บได้เฉพาะ:

- `device_id`, `company_id`, `brand_id`, `branch_id`, `station_key`, `shift_id`
- immutable `client_operation_id`, `idempotency_key`, schema version และเวลาที่เครื่องสร้าง
- product/variant/qty/modifier/note/customer display แบบลดข้อมูลส่วนบุคคล
- cached menu/price/tax display snapshot พร้อม `snapshot_version`, `expires_at`, `stale_at`
- payment intent เฉพาะ `cash`; ห้ามเก็บข้อมูลบัตร, provider secret, approval token หรือ tax credential
- request hash, retry count, last error และ Server acknowledgement

ทุก record เข้ารหัสด้วย storage mechanism ของ runtime เมื่อมี และลบตาม retention หลัง Server
acknowledge + reconciliation สำเร็จ ห้ามใช้ local timestamp เพื่อออกเลขบิลจริงหรือเรียงลำดับบัญชี

## 4. Outbox contract

State หลัก:

`draft_local → pending_sync → syncing → server_acknowledged → reconciled → purged`

State ที่ต้องหยุดให้คนตรวจ:

`needs_review`, `rejected`, `quarantined`, `expired`

Envelope ขั้นต่ำ:

```json
{
  "schema_version": "offline-pos-v1",
  "client_operation_id": "uuid",
  "idempotency_key": "offline-sale:<device-id>:<uuid>",
  "request_hash": "sha256",
  "company_id": "uuid",
  "brand_id": "uuid",
  "branch_id": "uuid",
  "station_key": "counter-01",
  "shift_id": "uuid",
  "operation_type": "cash_sale|hold_draft",
  "sequence_no": 1,
  "created_at_device": "RFC3339",
  "price_snapshot_version": "string",
  "payload": {},
  "retry": {"attempt": 0, "next_at": null, "last_error_code": null}
}
```

Server ต้องตรวจ Company/Brand/Branch/Device/Shift scope, schema, hash, idempotency, permission snapshot,
price/tax version และ inventory policy ใหม่ทุกครั้ง ห้าม client ส่งยอดสุทธิเป็น authority

## 5. Idempotency, retry และ lost acknowledgement

- unique key ฝั่ง Server คือ `(company_id, branch_id, client_operation_id)` และเก็บ canonical request hash
- key เดิม + hash เดิมคืนผลเดิม; key เดิม + hashต่างคืน `duplicate_request`
- network error/timeout ใช้ exponential backoff + jitter; 1s, 2s, 5s, 10s, 30s และสูงสุด 5 นาที
- HTTP 4xx เชิง business ไม่ auto retry; เปลี่ยนเป็น `needs_review` พร้อม machine-readable code
- HTTP 5xx/timeout retry ได้ แต่ต้อง inquiry ด้วย idempotency key ก่อนสร้าง request ใหม่
- lost acknowledgement ต้องถาม Server ด้วย client operation ID; ห้ามสร้างเลขใหม่เพื่อ “ลองอีกครั้ง”
- worker ส่งทีละ Branch/Shift ตาม `sequence_no`; รายการที่ conflict ไม่บล็อกการ inquiry แต่บล็อก close shift

## 6. Conflict resolution

| Conflict | ผลลัพธ์ |
| --- | --- |
| ราคา/ภาษี/โปรโมชันเปลี่ยน | `needs_review`; แสดงยอด Local เทียบ Server และให้พนักงาน/ลูกค้ายืนยันใหม่ |
| สินค้าปิดขาย/หมด/สต๊อกไม่พอ | `needs_review`; ห้ามติดลบหรือ substitute อัตโนมัติ |
| สิทธิ์/กะ/Device ถูก revoke หรือหมดอายุ | `rejected`; ห้าม retry จน login/pair/open shift ใหม่ |
| duplicate request hash เดิม | ใช้ Server result เดิมและ mark acknowledged |
| duplicate key แต่ payload ต่าง | quarantine และแจ้ง Manager |
| Server มี order แล้วแต่ client ไม่ได้รับ ack | inquiry แล้ว link order เดิม; ห้ามสร้าง Sale/Payment/Stock ซ้ำ |
| Local hold กับ Server hold ถูกแก้คนละฝั่ง | `needs_review`; ไม่มี last-write-wins หรือ auto-merge |
| Payment provider/Refund state unknown | ห้ามทำ offline; online inquiry/manual review เท่านั้น |

## 7. Reconnect state machine

`offline → probing → authenticating → refreshing_context → uploading → awaiting_ack → reconciling → online`

ถ้า token/device/shift invalid ให้เข้า `blocked_auth`; ถ้าราคา/สต๊อก/permission เปลี่ยนให้เข้า `needs_review`;
ถ้าผลไม่ทราบให้เข้า `unknown` และ inquiry เท่านั้น UI ต้องแสดง queue count, current item, last sync,
retry time และปุ่ม `ตรวจสอบกับ Server` โดยไม่ใช้คำว่า “สำเร็จ” ก่อน `reconciled`

## 8. UI states สำหรับ Desktop/iPad

- Banner ติดบนทุกหน้าขาย: Online, Offline, Reconnecting, Pending sync, Needs review, Stale, Permission denied
- Offline banner ต้องมี queue count และเวลา menu/price snapshot; สีไม่เป็นตัวสื่อความหมายเพียงอย่างเดียว
- ปุ่มต้องมี touch target อย่างน้อย 44×44 px, focus visible, keyboard navigation และ screen-reader label
- ปุ่มที่ห้าม offline เช่น QR payment, Refund, Approval, Tax document และ Close shift ถูก disable พร้อมเหตุผล
- หน้า Sync Center แยก Pending, Syncing, Needs review, Rejected และ Reconciled พร้อมรายละเอียดที่ไม่เผย secret
- ห้าม toast “ขายสำเร็จ” สำหรับ local pending; ใช้ “บันทึกในเครื่อง รอส่ง Server”

## 9. Feature gate และ Kill Switch

- `POS_OFFLINE_MODE_ENABLED=false` เป็นค่าเริ่มต้นทุก environment
- เปิดได้เฉพาะ UAT development hostname ที่ขึ้นต้น `uat-`, Company allow-list, Branch allow-list และ paired device
- Production validator ปฏิเสธ flag นี้จน Phase Gate, Security Owner และ Finance/Tax Owner ลงนาม
- Kill Switch ฝั่ง Server ปิดการรับ operation ใหม่ทันที แต่ยังเปิด inquiry/export outbox เพื่อกู้ข้อมูล
- Client ที่พบ flag ปิดต้องหยุด worker, ไม่ลบ queue และแสดง `Offline processing disabled`

## 10. Production blockers

- physical network-loss/lost-ack test บน Desktop/iPad และ browser lifecycle จริง
- encrypted local store + logout/revoke wipe policy ผ่าน security review
- cash operator reconciliation, duplicate receipt และ shift recovery ผ่าน Finance Owner
- loyalty reserve/commit/release เป็น atomic contract
- provider inquiry/refund unknown state และ tax/Credit Note gate ของ WP46 ผ่าน
- monitoring/alert, support runbook, backup/restore และ incident ownership พร้อม

## 11. Explicit non-actions

- ไม่เปิด Offline Mode ใน UAT รอบนี้
- ไม่รองรับ offline QR/PromptPay/card/refund/approval/tax/Credit Note
- ไม่เปลี่ยน Retail data source หรือ Production flags
- ไม่ส่ง Takeaway/Central Kitchen transaction ไป Production
