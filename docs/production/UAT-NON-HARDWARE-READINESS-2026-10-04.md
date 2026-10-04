# UAT Non-Hardware Readiness — 2026-10-04

## Decision

**Not approved for Production yet.** Automated non-hardware gates completed below, but physical Android testing, role-based human UAT, and the Restaurant `superadmin` identity defect remain open.

Production was not changed by this rehearsal.

## Release under test

- UAT commit: `18928aa24c601d33071f21e9bdfd06b2752bee29`
- Backend image: `restaurant-pos-backend:uat-store-hardening-18928aa`
- Frontend image: `restaurant-pos-frontend:uat-store-hardening-18928aa`
- Takeaway APK: `1.1.0-uat.8` (`version_code=10107`, minimum supported `10107`, rollback `10106`)

## Passed evidence

### Backup and isolated restore

- Backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/non-hardware-readiness-20261004T045726Z`
- SHA-256 validation: passed for five database dumps, uploads, Redis, and the Takeaway manifest.
- Restored into temporary databases: `legacy`, `platform_core`, `restaurant`, `retail`, and `takeaway`.
- Migration heads and per-table row-count fingerprints matched every source database.
- Restore time: 47 seconds.
- Temporary databases remaining: 0.
- Live source databases modified: no.

### Full API business flow

Passed on a fresh isolated Compose database:

`QR order -> kitchen -> payment -> recipe stock -> accounting journal -> ERP report`

The test reconciled one payment, one outbox event, one balanced journal, three recipe stock movements, and a THB 169.00 sale/report total.

### Offline, reconnect, and exactly-once behavior

Passed with a paired Counter on a fresh isolated Compose database:

- 100 offline cash orders in batches of 50.
- 100 sales, payments, dining sessions, accounting journals, and outbox events.
- 300 recipe stock movements.
- THB 16,900.00 reconciled total.
- 10 lost-acknowledgement replays returned the existing canonical sale IDs and created no duplicates.
- 20 simulated network transitions.
- Tampered payload: quarantined.
- Cross-tenant payload: quarantined.
- Offline PromptPay: rejected by policy.
- Revoked Counter credential: rejected.
- Targeted offline runtime tests: 14 passed.

Local evidence directory: `/private/tmp/restaurant-nonhardware-wp47-20261004T080220Z`.

### UAT runtime health

- `uat-app`, `uat-pos`, `uat-restaurant`, `uat-retail`, and `uat-takeaway`: root, `/health`, and `/health/ready` returned HTTP 200 from the UAT host.
- Backend, PostgreSQL, and Redis: healthy.
- Restart count: 0 for all six UAT containers.
- Root filesystem: 29% used.
- The initial HTTP-pattern scan returned zero matches, but traceback inspection found the known `superadmin` shift-opening HTTP 500 documented as `UAT-RDY-001`; the monitoring pattern must be widened before it can be used as a clean 5xx gate.
- TLS certificates were valid through 2026-11-07 at the snapshot.
- Signed Takeaway manifest returned JSON at `/downloads/takeaway-store/latest.json`.

### Dependency remediation prepared on this branch

- Backend: updated `PyJWT` from 2.13.0 to 2.15.1; `pip-audit` changed from 13 known findings to 0.
- Frontend: updated `Axios` from 1.18.1 to 1.20.0 and moved the build-only `tailwindcss-animate` package to `devDependencies`; `npm audit --omit=dev` changed from 6 affected production packages to 0 vulnerabilities.
- Backend regression: 613 passed, 1 skipped.
- Frontend type-check and production build: passed.
- Full development dependency audit still reports 10 findings in build/test tooling. A Tailwind 4 migration is the proposed breaking upgrade and requires a separate compatibility review; these packages are absent from the production dependency audit.

These dependency updates are verified in the readiness branch but are not deployed to UAT or Production yet.

## Open defects

### UAT-RDY-001 — `superadmin` cannot open a Restaurant cashier shift

Severity: release blocker for the stated all-function `superadmin` test plan.

The Platform identity for `superadmin` is not present in the legacy operational `users` table currently used by `RESTAURANT_SERVICE_DATABASE=legacy`. Opening a Restaurant cashier shift attempts to insert that Platform user ID into `cashier_shifts.user_id` and fails the `fk_cashier_shifts_user_id_users` foreign key.

Observed result: `POST /api/v1/pos/shifts/open` returned HTTP 500 at `2026-10-04T05:24:46Z`.

Required resolution: define and test a supported identity projection or operational actor mapping for Platform users before using `superadmin` across Restaurant operations. Do not remove the foreign key or silently substitute another user.

### UAT-RDY-002 — readiness harness drift

The previous rehearsal harness passed an empty optional UUID, ran source-contract tests without mounting repository source, and invoked an obsolete offline load client without a paired Counter token. The harness has been updated to use a valid inert QA UUID, mount the repository read-only for regression tests, and execute the paired-device WP47 offline gate.

### UAT-RDY-003 — verified dependency updates are not deployed

The deployed UAT images still identify release commit `18928aa24c601d33071f21e9bdfd06b2752bee29`. The zero-production-vulnerability dependency updates above must be reviewed, merged, deployed to UAT, and followed by regression/UAT reruns before Production approval.

## Still requires people or hardware

- Android device: install/update from an older APK, forced minimum-version flow, download/install/relaunch, Bluetooth printer, drawer, loss/recovery of connectivity, and long-receipt behavior on the target device.
- Restaurant staff: table/QR/order/kitchen/change/cancel/refund/close-shift using real operating steps.
- Retail staff: barcode/weighted goods/discount/hold/return/cash and non-cash/close-shift.
- Manager: approvals, limits, void/refund, reports, branch isolation, and audit trail.
- Accounting/owner: VAT, journals, stock valuation, reconciliation, end-of-day reports, and export acceptance.
- Multi-company tester: switch Company/Brand/Branch and confirm no cross-tenant data leakage.

## Approval conditions

Production approval requires all of the following:

1. Resolve `UAT-RDY-001` and rerun Restaurant tests with `superadmin`.
2. Review, merge, and deploy the dependency updates; rerun the automated and UAT gates.
3. Record named human UAT owners and results for Restaurant, Retail, Manager, Accounting, and multi-company isolation.
4. Complete Android physical-device evidence when the device arrives.
5. Assign monitoring and rollback owners and widen the 5xx log matcher.
6. Record the final go-live decision in `docs/production/sign-off.md`.
