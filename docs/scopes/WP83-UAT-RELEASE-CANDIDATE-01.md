# WP83 — UAT Release Candidate and Production Write Gate

วันที่: 2026-09-27

สถานะ: **IN PROGRESS — UAT ONLY; Production unchanged**

## เป้าหมาย

- สร้าง Backend และ Frontend จาก release commit เดียวกัน
- รักษาธุรกรรม UAT ของ WP82 ไว้โดยไม่ seed หรือสร้าง Company/Brand/Branch ซ้ำ
- เปลี่ยน Takeaway write gate ให้เป็น server-authoritative mode:
  `hold`, `uat`, `canary`, `live`
- ให้ `hold` เป็นค่าเริ่มต้น และให้ Production canary ต้องมี Company, Brand,
  Branch allowlist พร้อม approval reference ครบทุกค่า
- ซ้อม migration/backup/rollback โดยไม่แก้ Production

## WP82 baseline ที่ต้อง reuse

- Evidence commit: `7d6cd1f`
- Baseline image: `restaurant-pos-*:wp81-78aee14`
- Existing order: `TW-20260923-1F3972-0088`
- Existing transfer: `TT-20260927-0004`
- Existing pre-activation backup: `wp82-before-live-uat-transactions-0c0302e`
- ห้าม copy UAT transaction IDs หรือข้อมูล transaction เข้า Production

## Release gate contract

| Mode | Runtime boundary | Result |
|---|---|---|
| `hold` | ทุก environment | mutation ตอบ `409 takeaway_write_hold` |
| `uat` | `development` + HTTPS `uat-*` เท่านั้น | อนุญาต UAT transactions |
| `canary` | `production` + HTTPS Production hostname | อนุญาตเฉพาะ signed context ที่ตรง Company/Brand/Branch allowlist |
| `live` | `production` + HTTPS Production hostname | ต้องมี approval reference; เปิดภายหลัง canary sign-off เท่านั้น |

Public Takeaway ordering ตรวจ context จาก ordering token ฝั่ง Server ส่วน staff
transactions ตรวจ Company/Brand/Branch จาก access token และ membership context ฝั่ง Server
จึงไม่เชื่อค่า tenant IDs ที่ส่งมาจาก client payload

## Automated evidence

- Takeaway gate unit tests: `10/10` ผ่าน
- Backend regression: `582/582` ผ่าน
- Frontend TypeScript type-check: ผ่าน
- Frontend production build: ผ่าน
- WP82 backup SHA-256: ผ่านครบ 5 database dumps
- UAT migration heads ก่อน deploy:
  - Legacy `wp65govern0026`
  - Platform `p15platform0019`
  - Restaurant `p6restaurant0007`
  - Retail `p13retail0007`
  - Takeaway `p6takeaway0008`

## UAT deployment boundary

- Deploy เฉพาะ UAT ด้วย Backend/Frontend tag เดียวกัน
- รักษา `TAKEAWAY_UAT_TRANSACTION_WRITES_ENABLED=true` ระหว่าง compatibility wave
- `TAKEAWAY_TRANSACTION_WRITE_MODE=hold` จะ resolve เป็น `uat` เฉพาะ UAT legacy flag
- ไม่เปลี่ยน Production images, flags, databases, hostnames หรือ provider modes
- Smoke test เริ่มจาก read-only verification ของ WP82 order/transfer เดิมก่อน
- ไม่ทำ physical printer, cash drawer, PromptPay หรือ card-provider acceptance ใน WP83

## Stop conditions

- image tag/digest หรือ release commit ไม่ตรงกัน
- migration head เปลี่ยนโดยไม่อยู่ใน release manifest
- backup checksum/restore validation ไม่ผ่าน
- WP82 order/transfer เดิมหายหรือยอดเปลี่ยนระหว่าง read-only verification
- gate ยอมให้ cross-company, cross-brand หรือ cross-branch mutation
- Production container หรือฐานข้อมูลมีการเปลี่ยนแปลง

## Rollback

1. คืน UAT Backend/Frontend เป็น WP82 image คู่เดิม
2. ตรวจ health และ WP82 read-only evidence
3. Restore database เฉพาะเมื่อได้รับคำสั่งแยกจาก Owner เพราะ restore จะลบ
   ธุรกรรม UAT หลัง backup
