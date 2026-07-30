# UI Redesign Plan — POS Module

**วันที่:** 2026-05-31 | **ไฟล์หลัก:** `frontend/src/pages/pos/POSPage.tsx`

---

## ปัญหาที่พบใน UI ปัจจุบัน

| # | ปัญหา | ผลกระทบ |
|---|------|---------|
| 1 | **Header ใหญ่เกินไป** — logo + branch + stat cards + buttons อยู่รวมกัน | เสีย vertical space มาก โดยเฉพาะหน้าจอเล็ก |
| 2 | **ปุ่ม "ชำระเงิน" ต้องเลื่อนไปหา** — อยู่ล่างสุด sidebar ไม่ sticky | cashier ต้อง scroll ทุกครั้งที่จะ checkout |
| 3 | **Customer form กินพื้นที่มาก** — ชื่อ/เบอร์/เลขภาษี/หมายเหตุ แสดงตลอดเวลา | บังรายการสินค้าในตะกร้า |
| 4 | **Step indicator (1/2/3)** — เป็น static ไม่ interactive | เสียพื้นที่โดยไม่เพิ่ม value |
| 5 | **Cart item แสดง VAT type และราคาปกติ** — ข้อมูลรอง | visual noise ระหว่างขาย |
| 6 | **window.confirm()** — native browser dialog | ดูไม่ consistent กับ design system |
| 7 | **Product card ใหญ่เกิน** — แสดง SKU + barcode + VAT type | จำนวนสินค้าต่อหน้าจอน้อย |
| 8 | **Split payment hidden ใน dashed box** | ลูกค้าค้นพบได้ยาก |

---

## การเปลี่ยนแปลงที่เสนอ (เรียงลำดับ Priority)

### P1 — Sticky Checkout Footer (ผลกระทบสูงสุด)

**เปลี่ยน:** ย้าย checkout summary + ปุ่มชำระเงินออกจาก scroll area มาเป็น fixed footer ของ sidebar

```
┌─ SIDEBAR ──────────────────────┐
│  [Cart Header] ตะกร้า (3)     │
│  ─────────────────────────     │
│  [scrollable]                  │
│    Cart Items                  │
│    Customer Section (collapse) │
│    Payment Method              │
│    Cash Input / QR             │
│  ─────────────────────────     │
│  [sticky footer]               │
│    ยอดรวม: ฿1,250.00          │
│    ┌──────────────────────┐   │
│    │   ชำระเงิน ฿1,250   │   │  ← Always visible
│    └──────────────────────┘   │
└────────────────────────────────┘
```

**วิธีทำ:** เปลี่ยน `space-y-4 border-t ... px-5 py-4` section ล่างสุดของ aside ให้เป็น sticky

---

### P2 — Compact Header

**เปลี่ยน:** ลด header เหลือ 1 แถว โดยย้าย stat cards ไปอยู่ใน sidebar footer

```
Before (2 แถว ~120px):
┌──────────────────────────────────────────────────┐
│ Front Counter        [สินค้า 24] [ใกล้หมด 2]    │
│ Restaurant POS              [ยอดสุทธิ ฿1,250]           │
│ [สาขา][คลัง][กะ][ONLINE]                         │
│                      [ออเดอร์ล่าสุด][ปิดกะ][กลับ]│
└──────────────────────────────────────────────────┘

After (1 แถว ~64px):
┌────────────────────────────────────────────────────────────┐
│ Restaurant POS  [สาขาหลัก][S001][ONLINE]  [ล่าสุด][ปิดกะ][กลับ] │
└────────────────────────────────────────────────────────────┘
```

---

### P3 — Collapsible Customer Section

**เปลี่ยน:** Customer section collapse ได้ แสดงเฉพาะ chip ชื่อลูกค้าเมื่อเลือกแล้ว

```
ไม่มีลูกค้า:
[ + เพิ่มสมาชิก / ค้นหา ]   ← compact trigger

มีลูกค้าแล้ว:
[👤 สมชาย จ. ⭐ 450 pts  ×]   ← 1 chip เท่านั้น
```

---

### P4 — Compact Cart Items

**เปลี่ยน:** ลด padding + ซ่อน VAT type ไว้ใน tooltip แทน

```
Before:
┌─────────────────────────────┐
│ น้ำดื่ม 1.5L                │
│ รวม VAT 7%                  │
│ ราคาปกติ ฿15.00             │
│ [−] [1] [+]    ฿15.00      │
│                ฿15.00       │
└─────────────────────────────┘

After:
┌─────────────────────────────┐
│ น้ำดื่ม 1.5L     ×  แก้ราคา│
│ [−][1][+]        ฿15.00    │
└─────────────────────────────┘
```

---

### P5 — Product Card Density Options

**เปลี่ยน:** เพิ่มปุ่ม toggle ระหว่าง Grid (กะทัดรัด) และ List view

```
Grid Mode (default — มากขึ้นต่อหน้า):
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│[img] │ │[img] │ │[img] │ │[img] │ │[img] │
│ชื่อ  │ │ชื่อ  │ │ชื่อ  │ │ชื่อ  │ │ชื่อ  │
│฿15  │ │฿15  │ │฿15  │ │฿15  │ │฿15  │
└──────┘ └──────┘ └──────┘ └──────┘ └──────┘
(xl: 5 cols แทน 4 cols)
```

---

### P6 — Dialog แทน window.confirm()

**เปลี่ยน:** เปลี่ยน `window.confirm()` ทั้งหมดเป็น shadcn `AlertDialog`

จุดที่ต้องเปลี่ยน:
- ล้างตะกร้า (cart header)
- กลับ Dashboard (header back button)
- Resume held bill
- Begin exchange flow

---

### P7 — Split Payment Discovery

**เปลี่ยน:** เปลี่ยน checkbox + dashed box → toggle button ที่ชัดเจน

```
Before: [checkbox] เปิด split payment
After:  [⇄ แยกชำระ 2 ช่องทาง]  ← styled button
```

---

## Layout Overview (After)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ HEADER (64px) — Restaurant POS | สาขาหลัก | กะ001 | ONLINE | [ล่าสุด][ปิดกะ] │
├────────────────────────────────────────┬─────────────────────────────────┤
│  LEFT PANEL (flex-1)                   │  SIDEBAR (28rem)                │
│  ┌─────────────────────────────────┐   │  ┌─────────────────────────────┐│
│  │ [Search input]       [📷 สแกน] │   │  │ Header: ตะกร้า (3) [พักบิล]││
│  └─────────────────────────────────┘   │  ├─────────────────────────────┤│
│  [ทั้งหมด][เครื่องดื่ม][ขนม]...      │  │ scrollable:                 ││
│                                        │  │  Cart items (compact)       ││
│  [Exchange Banner if active]           │  │  ─────────────────────────  ││
│                                        │  │  [Customer chip/expand]     ││
│  ┌────┐┌────┐┌────┐┌────┐┌────┐       │  │  ─────────────────────────  ││
│  │    ││    ││    ││    ││    │       │  │  [Payment method buttons]   ││
│  │    ││    ││    ││    ││    │       │  │  [Cash input / QR]          ││
│  └────┘└────┘└────┘└────┘└────┘       │  │  [⇄ แยกชำระ]               ││
│  ┌────┐┌────┐┌────┐┌────┐┌────┐       │  ├─────────────────────────────┤│
│  │    ││    ││    ││    ││    │       │  │ STICKY FOOTER:              ││
│  └────┘└────┘└────┘└────┘└────┘       │  │  ยอด: ฿1,250 | ส่วนลด: ฿0 ││
│                                        │  │  ┌─────────────────────┐   ││
│                                        │  │  │  ชำระเงิน ฿1,250   │   ││
│                                        │  │  └─────────────────────┘   ││
└────────────────────────────────────────┴─────────────────────────────────┘
```

---

## ลำดับการ Implement

| ลำดับ | งาน | ไฟล์ | เวลาประมาณ |
|------|-----|------|------------|
| 1 | Sticky checkout footer (P1) | POSPage.tsx | 1 ชั่วโมง |
| 2 | Compact header (P2) | POSPage.tsx | 30 นาที |
| 3 | Collapsible customer section (P3) | POSPage.tsx | 1 ชั่วโมง |
| 4 | Compact cart items (P4) | POSPage.tsx | 30 นาที |
| 5 | AlertDialog แทน confirm (P6) | POSPage.tsx | 45 นาที |
| 6 | Split payment UX (P7) | POSPage.tsx | 20 นาที |
| 7 | Product card density (P5) | POSPage.tsx | 30 นาที |

---

*เริ่มจาก P1 ก่อนเพราะส่งผลต่อ UX มากที่สุด — cashier ทุกคนต้องกดชำระเงินทุก transaction*
