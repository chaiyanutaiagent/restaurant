# WP47 UAT Execution Report

Last updated: 2026-09-21
Environment: UAT deployed and engineering smoke completed
Production: untouched; no feature flags changed

## Release identity

- Branch: `codex/foodchainservice-platform`
- Application commit: `b329d2c`
- UAT smoke-harness commit: `e2b8101`
- UAT evidence label: `wp47-e2b8101`
- Migration: `wp47offline0023`
- Backend image: `restaurant-pos-backend:wp47-b329d2c`
  - digest: `sha256:188497804c811259454823995a71bdcff37698f414e18196051464ec24ac336d`
- Frontend image: `restaurant-pos-frontend:wp47-b329d2c`
  - digest: `sha256:1e143ae096204907c67ed622bc5a96597c05b558ef7b263a939140f36157de9a`

## Completed local checks

| Check | Result | Evidence |
|---|---|---|
| Python syntax parse | Pass | All backend application and migration source parsed |
| WP47 focused unit tests | Pass | 10/10 |
| WAP offline regression | Pass | 9/9 |
| Full backend unit regression | Pass | 438 passed, 1 skipped |
| Frontend TypeScript | Pass | `tsc --noEmit` |
| Frontend production build | Pass | Vite/PWA build |
| Blank DB migration | Pass | upgrade, downgrade to WP46, upgrade to WP47 |

## UAT deployment and recovery evidence

| Check | Result | Evidence |
|---|---|---|
| Pre-deploy backup | Pass | `/home/behappyaiagent/restaurant-uat-deploy-backups/wp47-before/restaurant-pos-uat-20260920T182449Z` |
| Backup verification | Pass | Five PostgreSQL custom dumps, Redis metadata and uploads archive passed checksums/catalog inspection |
| UAT migration | Pass | `wp46refund0022` → `wp47offline0023 (head)` |
| Public readiness | Pass | `https://uat-pos.foodchainservice.com/health/ready` returned HTTP 200 |
| HTTPS policy | Pass | HSTS, CSP, no-store and camera self policy present |
| Automatic offline/replay smoke | Pass | 100 orders, 10 lost-ack replays and 20 network transitions |
| Server parity | Pass | 100 Sales, 100 Payments, 100 Sessions, 100 Journals, 100 Outbox events, 300 Stock movements; total THB 16,900.00 |
| Security/exception cases | Pass | Offline PromptPay rejected, cross-tenant request quarantined, payload mismatch quarantined and resolved with audit, paired Counter revoked after smoke |
| Active queue after smoke | Pass | No active records; 100 reconciled and one intentional rejected hash-mismatch record retained as evidence |
| Browser smoke | Pass with data findings | POS and Physical UAT pages rendered at 1024×768 with no document-level horizontal overflow or console errors |
| Offline Sync access boundary | Pass | Unpaired browser redirected to Device Pairing before `/counter/sync` |
| App-only rollback rehearsal | Pass | WP47 → WP46 healthy in 10 seconds; WP46 → WP47 healthy in 11 seconds; additive WP47 schema retained |
| Production isolation | Pass | Production container IDs/images were unchanged before and after the UAT operation |

The UAT Docker Compose PostgreSQL container was recreated because the release directory changed, but the named volume was preserved and the database passed readiness and migration checks.

## Browser and UAT data findings

- The POS product selector contains duplicated category names and UAT/approval/raw-material records that should not be selectable as restaurant menu items.
- These are UAT catalogue-cleanup/filtering findings, not evidence of an offline-sync failure. They must be resolved before Business UAT sign-off.
- The Sync Center is intentionally unavailable until the browser is paired to an approved Counter.
- Browser inspection does not replace printer, scanner, cash drawer, PromptPay or real-device evidence.
- `UAT_AUTH_BYPASS_ENABLED=true` remains a temporary UAT convenience and must be disabled before formal permission/security sign-off.

## Remaining evidence

- Real paired Counter/iPad physical-device execution.
- Barcode/Table QR camera scanning.
- Customer receipt and kitchen printer output/failure/retry evidence.
- Cash drawer or Manager-approved N/A evidence.
- PromptPay Sandbox/UAT reconciliation while online.
- End-to-end Dine-in, Takeaway and offline cash recovery evidence.
- Separate submitter, Technical checker and Business checker approvals.

No manual hardware result may be inferred from automated browser or API evidence.

## Gate decision

- Engineering UAT gate: **PASS WITH DATA-CLEANUP FINDINGS**.
- Physical UAT gate: **PENDING**.
- Production decision: **NO-GO**.
