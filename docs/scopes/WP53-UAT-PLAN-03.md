# WP53 UAT Plan — Offline and Sync Recovery

Date: 2026-09-22  
Environment: `uat-pos.foodchainservice.com` only

## Automated gate

1. Frontend TypeScript check and production build.
2. WP53 static contract tests plus WP52 regression tests.
3. Existing offline/idempotency Backend regression tests where applicable.

## Browser UAT

1. Confirm paired Counter and signed Staff context can open `/pos/offline-sync`.
2. Confirm the empty state uses real browser storage and does not fabricate queue counts.
3. Add reversible, browser-local encrypted UAT fixtures for representative states only when needed.
4. Verify list/detail, identity, totals, timestamps, errors, print state and safe Support reference.
5. Verify pending and review counts link from Restaurant Takeaway POS.
6. Verify `unknown` offers inquiry, `needs_review` offers manager guidance/retry, and `syncing`
   prevents retry.
7. Verify offline copy states cash-only behavior and leaves existing paid evidence visible.
8. Verify desktop and 1024×768 tablet-landscape composition.

## Deployment and rollback gate

1. Build an immutable frontend image from the accepted commit.
2. Recreate only the UAT frontend service; Backend, database, nginx and Production remain unchanged.
3. Verify public UAT routes and health endpoints.
4. Roll UAT frontend back to the previous immutable image, verify health, then restore WP53.
5. Compare Production container identities before and after.

## Out of scope

Airplane mode, full browser/app restart, printer failure, cash drawer, real PromptPay/provider and
multi-device concurrency are physical WP54 tests and cannot be inferred from browser UAT.

