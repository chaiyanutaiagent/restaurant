# UAT Non-Hardware Readiness — 2026-10-04

## Decision

**Not approved for Production yet.** Automated non-hardware gates completed below, and the Restaurant `superadmin` identity fix is deployed and verified on UAT. Physical Android testing and role-based human UAT remain open.

Production was not changed by this rehearsal.

## Release under test

- UAT commit: `3760d604193ff35d3fda9ceb5e8f340f850dce02`
- Backend image: `restaurant-pos-backend:uat-readiness-3760d60`
- Frontend image: `restaurant-pos-frontend:uat-readiness-3760d60`
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

- After deployment of `3760d60`, `uat-app`, `uat-pos`, `uat-restaurant`, `uat-retail`, and `uat-takeaway`: root, `/health`, and `/health/ready` returned HTTP 200 from the UAT host.
- Backend, PostgreSQL, and Redis: healthy.
- Restart count: 0 for the replaced backend and frontend containers.
- Root filesystem: 29% used.
- The post-deployment backend scan for tracebacks, foreign-key violations, internal-server errors, and `status=5xx` returned zero matches.
- TLS certificates were valid through 2026-11-07 at the snapshot.
- Signed Takeaway manifest returned JSON at `/downloads/takeaway-store/latest.json`.

### UAT `superadmin` operational identity

The untouched UAT backup first reproduced the missing legacy actor. A clone-only smoke then passed:

`Platform superadmin -> session issuance -> canonical user projection -> Restaurant cashier shift`

After deploying `3760d60`, the same path passed on live UAT. The temporary verification session was revoked, shift `b6f8e130-151a-4bae-93d0-ac26e740c8e6` (`S20261004-001`) opened with zero cash and closed cleanly, and no test shift remains open. The shift retained canonical Platform user ID `8b45ab10-41ca-4aed-8e90-662f39392996` as its audit actor.

### Dependency remediation deployed to UAT

- Backend: updated `PyJWT` from 2.13.0 to 2.15.1; `pip-audit` changed from 13 known findings to 0.
- Frontend: updated `Axios` from 1.18.1 to 1.20.0 and moved the build-only `tailwindcss-animate` package to `devDependencies`; `npm audit --omit=dev` changed from 6 affected production packages to 0 vulnerabilities.
- Backend regression after the `superadmin` transition bridge: 615 passed, 1 skipped.
- Frontend type-check and production build: passed.
- Full development dependency audit still reports 10 findings in build/test tooling. A Tailwind 4 migration is the proposed breaking upgrade and requires a separate compatibility review; these packages are absent from the production dependency audit.

These dependency updates and the `superadmin` transition bridge are deployed to UAT. The live backend reports PyJWT 2.15.1. They are not deployed to Production.

## Resolved readiness items

### UAT-RDY-001 — `superadmin` could not open a Restaurant cashier shift

Severity: release blocker for the stated all-function `superadmin` test plan.

The Platform identity for `superadmin` was not present in the legacy operational `users` table used by `RESTAURANT_SERVICE_DATABASE=legacy`. Opening a Restaurant cashier shift attempted to insert that Platform user ID into `cashier_shifts.user_id` and failed the `fk_cashier_shifts_user_id_users` foreign key.

Observed result: `POST /api/v1/pos/shifts/open` returned HTTP 500 at `2026-10-04T05:24:46Z`.

Resolution: the exact gated UAT `superadmin` login synchronously mirrors the canonical Platform user ID and password hash into the legacy operational `users` table while Restaurant still uses `RESTAURANT_SERVICE_DATABASE=legacy`. The existing foreign key and audit actor are preserved; projection failure returns HTTP 503 rather than issuing a partially usable session. The bridge becomes a no-op after Restaurant database cutover.

Clone verification used the untouched UAT backup listed above, restored to separate `uat_fix_platform` and `uat_fix_legacy` databases. The backup reproduced the missing legacy user, then `backend/tests/smoke_uat_superadmin_legacy_projection.py` passed the complete transition path:

`Platform superadmin -> session issuance -> canonical user projection -> Restaurant cashier shift`

The clone result retained Platform user ID `8b45ab10-41ca-4aed-8e90-662f39392996` as its audit actor. Deployment and the bounded live UAT session/open/close verification also passed on `3760d60`. Production was not modified.

### UAT-RDY-002 — readiness harness drift

The previous rehearsal harness passed an empty optional UUID, ran source-contract tests without mounting repository source, and invoked an obsolete offline load client without a paired Counter token. The harness has been updated to use a valid inert QA UUID, mount the repository read-only for regression tests, and execute the paired-device WP47 offline gate.

### UAT-RDY-003 — verified dependency updates were not deployed

Resolved on UAT by release `3760d60`. Production dependency audit remains at zero known vulnerabilities, while the documented build/test-only findings remain deferred to the separate Tailwind 4 compatibility review.

## Still requires people or hardware

- Android device: install/update from an older APK, forced minimum-version flow, download/install/relaunch, Bluetooth printer, drawer, loss/recovery of connectivity, and long-receipt behavior on the target device.
- Restaurant staff: table/QR/order/kitchen/change/cancel/refund/close-shift using real operating steps.
- Retail staff: barcode/weighted goods/discount/hold/return/cash and non-cash/close-shift.
- Manager: approvals, limits, void/refund, reports, branch isolation, and audit trail.
- Accounting/owner: VAT, journals, stock valuation, reconciliation, end-of-day reports, and export acceptance.
- Multi-company tester: switch Company/Brand/Branch and confirm no cross-tenant data leakage.

## Approval conditions

Production approval requires all of the following:

1. Record named human UAT owners and credential-based results for Restaurant, Retail, Manager, Accounting, and multi-company isolation.
2. Complete Android physical-device evidence when the device arrives.
3. Assign monitoring and rollback owners and retain the widened `status=5xx` log matcher.
4. Merge the UAT candidate after review and record the final go-live decision in `docs/production/sign-off.md`.
