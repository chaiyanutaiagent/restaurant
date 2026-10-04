# WP54 UAT Plan — Counter Readiness and Physical Evidence

Date: 2026-09-22
Environment: `uat-pos.foodchainservice.com` only

## Engineering gate

1. TypeScript check and production frontend build.
2. WP54, WP53 and WP52 contract regression tests.
3. Verify the UAT-only API flag and Production rejection remain intact.
4. Verify automatic checks cannot be manually overridden, evidence is secret-filtered and approved
   sessions are immutable.

## Browser preflight

1. Use the paired `UI-DEVICE-01` Counter and existing UAT Staff session.
2. Create a UAT session for the current frontend release without inventing physical evidence.
3. Confirm automatic checks refresh from Server and manual checks remain `ยังไม่ยืนยัน`.
4. Confirm blockers keep `ส่งตรวจ Gate` disabled.
5. Confirm Release/Counter/OS/Browser/Printer/Network snapshot and safe evidence instructions.
6. Inspect desktop and 1024×768 tablet composition.

## Physical execution

The Product Owner/operator must perform these on the target hardware and attach approved evidence:

- Airplane/Wi-Fi/LTE loss, reconnect, local pending queue, lost acknowledgement and one canonical result.
- Product barcode and Table QR camera/scanner.
- Customer receipt, kitchen slip, paper-out/reconnect/reprint and cash drawer or approved N/A.
- PromptPay Sandbox reference/reconciliation.
- Dine-in, Takeaway, KDS and Pickup flow on intended devices.
- Multi-device concurrency and downstream row parity.

Untested physical rows remain pending; Browser smoke cannot mark them passed.

## Deployment and rollback

Deploy an immutable UAT frontend image only unless a reviewed Backend change becomes necessary. Rehearse
frontend rollback/restore, verify health and compare Production container identities before/after.

