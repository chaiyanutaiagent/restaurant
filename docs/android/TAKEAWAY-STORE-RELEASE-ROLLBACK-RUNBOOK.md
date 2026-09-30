# Takeaway Store release and recovery runbook

This checklist is for the operator and QA approving a future Store release.
It does not authorize deployment. This work package changed no UAT runtime and
no Production state. Baseline evidence is in
[the September 30 audit](TAKEAWAY-STORE-HARDENING-AUDIT-20260930.md).

## Before release approval

- [ ] Record approver, target environment, source SHA, exact image digests, APK
  package/version, signed manifest and signer certificate fingerprint.
- [ ] Confirm repository is `chaiyanutaiagent/restaurant` and remote is `origin`.
  Never use the legacy ERP-POS repository as a release destination.
- [ ] Complete candidate unit/browser/native tests. Do not redistribute local
  verification artifacts signed/configured with a disposable test public key.
- [ ] Assign a strictly increasing APK version code. Do not replace the existing
  UAT 7 APK or republish changed bytes under version `10106`.
- [ ] Confirm UAT and Production packages, release public keys and hosts remain
  separate. Production package is `com.foodchainservice.takeaway`; UAT is `.uat`.
- [ ] For Production, all test-login flags and frontend automatic-login switches
  must be false; startup with any enabled UAT-only mode must fail closed.
  Audit employee passwords separately; no universal test account is approved.
- [ ] Keep `android:apk:release` and Gradle Production HOLD in place until a
  separately approved signing/go-live change. Debug certificates are UAT only.
- [ ] Record the tenant/branch transaction allowlist, customer approval, backup
  point and expected outage. This candidate does not open transaction flags.
- [ ] Confirm monitoring recipients and an operator who can pause rollout.

## Backup validation and recovery rehearsal

1. Resolve the exact Compose project and database names before any backup or restore.
   Record live container IDs/images without exposing environment secrets.
2. Preserve database dumps for all five boundaries, uploads, Redis and the exact
   compose/environment configuration. Store secrets under restricted permissions.
3. Validate `sha256sum -c SHA256SUMS` and `pg_restore --list` for every dump. Check
   archive members and sizes; an unexpectedly empty upload archive is a blocker.
4. With separate approval, restore into an isolated scratch PostgreSQL instance
   with no application workers, payment credentials or outbound notifications.
   Never use UAT or Production as the scratch restore target.
5. Compare migration heads, tenant counts, critical catalog/order/stock/payment
   totals and uploaded-image references against the captured backup snapshot.
   Record actual measured recovery time; do not invent RTO/RPO targets.
6. Confirm an encrypted off-host copy, access owner and retention policy. File
   existence alone does not certify encryption or restorability.

The current audit verified checksums and dump readability only. A restore is
pending approval and must not be implied by a successful checksum check.

## Controlled UAT deployment after approval

1. Capture before-state metadata and a fresh verified backup. Record unsynced
   device queues; do not clear browser/device storage to make a rollout pass.
2. Confirm migration compatibility. `p6takeaway0009` added catalog display columns;
   prefer retaining additive columns for application rollback. Do not blindly
   downgrade the schema or restore an old database over later sales.
3. Replace only the approved backend/frontend services using the existing
   `restaurant-pos-uat-drill` project and correct compose overlays. Preserve
   database, Redis, nginx and tunnel services. Never run stack-wide teardown.
4. Check health, image digests, restart counts and migration head. Perform a
   read-only signed Store smoke with redacted credentials. Request writes only
   for explicitly approved UAT transactions.
5. Publish a versioned APK first; verify package, certificate, checksum and signed
   manifest from the public URL, then change the channel pointer atomically.
6. Run the device acceptance checklist below and compare Production metadata to
   the pre-release snapshot. Stop on any cross-company or financial inconsistency.

## Rollback decisions

| Failure | Safe recovery approach | Required safeguard |
| --- | --- | --- |
| Backend/frontend regression | Redeploy the exact saved image digests in the UAT project | Approval, schema compatibility and new-write reconciliation |
| Invalid update manifest | Restore the last verified channel pointer | Check version floor and certificate; it will not downgrade already updated devices |
| Already installed faulty APK | Build known-good source as a NEW higher version, signed with the same installed key | Test local database/queue compatibility and device installation |
| Corrupted database | Restore into scratch, reconcile new transactions, obtain explicit restore approval | Never overwrite recent payments/sales from an older snapshot without reconciliation |

`rollback_version_code` is an operator reference, not permission to downgrade.
UAT 7 requires `10106`, while UAT 6 is `10105`. Changing `latest.json` to UAT 6
does not revert UAT 7 installations. The updater refuses equal/lower versions.
Uninstall/reinstall can destroy offline queues and is not the default recovery.
Do not lower the minimum version casually or reuse a version code.

After recovery, recheck health, revision, catalog, scoped permissions, order and
payment reconciliation, unsynced queues and manifest/artifact hashes. Record the
actual result and approver; retain failed-release evidence.

## Monitoring and alerts to configure

These are proposed checks, not an installed monitoring service. Assign owners
and thresholds before Production and verify alert delivery with one controlled test.

| Signal | Proposed action | Owner role |
| --- | --- | --- |
| Readiness unavailable for 2 consecutive one-minute checks | Stop rollout, investigate dependencies | Operations |
| New restart, OOM or exit 139 | Capture redacted logs and resource metrics; investigate immediately | Operations |
| New 5xx or sustained error-rate increase | Compare against baseline; pause rollout | Backend on-call |
| Cross-company context denial spike or any confirmed exposure | Stop affected tenant operations and escalate | Security and CTO |
| Manifest signature/hash/package mismatch | Block publication/install, investigate artifacts | Release owner |
| Offline queue stuck after connectivity recovers | Preserve device storage and reconcile duplicates/stock | Support and QA |
| Missing backup, checksum failure or unexpected empty uploads | Block release until recovered | Operations |
| Health version differs from release metadata | Correct through approved deployment; use image digest meanwhile | Release owner |

Collect aggregate metrics, not passwords, access tokens or full payment payloads.
The update prompt currently ignores feed/network failures to preserve offline
sales; this is availability behavior, not an enforceable server-side revocation
policy for outdated devices.

## Physical UAT acceptance record

All rows start **PENDING**. QA records tester/date, device/OS, APK version, company,
branch, evidence and transaction IDs. Use approved UAT payment paths only.

| Scenario | Pass condition |
| --- | --- |
| Install and update | Existing UAT app accepts same-signer higher version; permissions/cancel/retry behave correctly |
| Cross-company onboarding | Same APK signs into two authorized companies; wrong credentials/branch cannot cross scope |
| Employee roles | Cashier, receiving, branch manager, owner and central-kitchen denial match assigned duties |
| Catalog and photos | Category/search/barcode/description/price/images and image-error fallback render correctly on tablet |
| Stock and reservations | Sale cannot consume reserved or missing stock; displayed availability matches sale location |
| Cash and drawer | Tender/change and shift totals reconcile; drawer opens only on intended actions |
| PromptPay | Verified payment appears once; cancel/timeout/retry do not duplicate or falsely mark paid |
| Receipt printer | Customer/merchant copies, Thai text, paper length, reprint marker and print count are correct |
| Scanner | Actual keyboard-wedge/camera device locates intended SKU without duplicate additions |
| Network loss | Queued sales survive restart and reconnect; retry does not duplicate stock/payment/sale |
| Logout and switch | Unsynced sales block destructive cleanup; after sync no prior-company data is shown |
| Recovery | Approved forward rollback preserves queues/session/data and reconciles totals |

No combination of mocked browser tests, native unit tests or HTTP 200 replaces
these physical acceptance checks.
