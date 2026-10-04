# WP54 Coverage Matrix — Counter Readiness and Physical UAT

Date: 2026-09-22

| Area | System evidence | Physical evidence required | Gate behavior |
| --- | --- | --- | --- |
| Counter identity | Pairing, Company/Branch, revoke, last seen | Restart/reopen on target Counter | Required |
| Release | Configured UAT release comparison | PWA/app cache shows the candidate | Required |
| Staff and shift | Open shift count and scoped identity | Handover with target staff | Required |
| Sync queue | Server pending/unknown/review count | Local Outbox and reconnect observation | Required |
| Offline authorization | Signed lease in POS runtime | Cash sale while disconnected | Required |
| Lost acknowledgement | Inquiry/replay contract | Cut after commit before response | Required |
| Product barcode | Browser flow exists | Camera/scanner, lighting and focus | Required |
| Table QR | Table route exists | Scan correct table/brand on device | Required |
| Customer receipt | Preview/print flow exists | Thai, totals, identifier, paper/feed/cut | Required |
| Kitchen slip/KDS | KDS route and job API exist | Printer/display readability and sound | Required |
| Printer recovery | Idempotent receipt/order contract | Paper-out/disconnect/reconnect/reprint | Required |
| Cash drawer | No verified integration | Target hardware, or approved N/A reason | Required/N/A |
| PromptPay | QR and UAT configuration | Sandbox payment reference/reconcile | Required |
| Dine-in | Table/KDS/payment routes | End-to-end on target devices | Required |
| Takeaway | Queue/KDS/Pickup routes | End-to-end on target devices | Required |
| Multi-device | Scoped device credentials | Concurrent Counter/KDS/Pickup observation | Required |
| Row parity | Server canonical records available | Sale/Payment/Stock/Journal/Event/Tax/Loyalty comparison | Required |
| Rollback | Immutable images and health checks | Operator ownership and recovery drill | Required |

## Status vocabulary

- `ระบบตรวจ ณ เวลานี้` — evidence comes from the API/runtime and can become stale.
- `ยังไม่ยืนยัน` — no physical tester evidence; this remains a blocker.
- `ผ่านพร้อมหลักฐาน` — a named tester recorded an evidence reference against this Release/Device.
- `ไม่ผ่าน` — a defect ID and severity are required.
- `ไม่ใช้กับสาขานี้` — allowed only for Cash drawer with an approved reason.

No matrix row can enable Production. Production remains a separate owner decision.

