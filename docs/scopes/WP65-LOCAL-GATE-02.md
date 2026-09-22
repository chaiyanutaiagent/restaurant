# WP65 Local Engineering Gate

Date: 2026-09-23
Decision: **LOCAL PASS / IMMUTABLE UAT CANDIDATE MAY BE CREATED**
Production decision: **NO-GO / unchanged**

## Initial independent QA findings and closure

The first QA audit returned NO-GO for plaintext webhook secrets, query-string and
wildcard API keys, missing key ownership/expiry, missing replay protection,
missing retry/dead-letter, client-authoritative external pricing, incomplete
states and absent Retail/Integration E2E. All release-blocking findings were
closed in the WP65 candidate before this gate.

## Automated evidence

- Backend regression: 564 passed, 1 skipped.
- WP65 integration/governance contract tests: 11 passed.
- Frontend TypeScript: passed.
- Frontend production build: passed; the existing non-blocking chunk-size warning
  remains.
- Browser regression: 46 passed:
  - Platform 20
  - Company/Governance 7
  - Company Kitchen 2
  - Distribution 2
  - Takeaway 6
  - Public Customer Experience 6
  - Integration 2
  - Retail desktop/tablet 1
- Local Backend runtime: `/health`, `/health/live` and `/health/ready` returned
  healthy responses from the rebuilt image.
- Secret migration dry-run and apply completed without exposing or changing a
  secret in the empty Local integration dataset.

The first full backend run mounted only `backend/` and failed tests that resolve
fixtures from the repository root. Re-running the same suite with the complete
repository mounted passed 564/564 runnable tests; this was a test-harness mount
error, not a product failure.

## Local backup and migration rehearsal

Pre-migration backup roots:

- `backups/wp65-pre-migration/restaurant-pos-local-20260922T174935Z`
- `backups/wp65-pre-migration/restaurant-boundaries-local-20260922T174948Z`

The boundary backup contains Platform, Restaurant, Retail and Takeaway dumps and
checksums. The Legacy/Shared ERP backup is separate. Upgrade, one-step downgrade
and re-upgrade passed; all five database heads match the WP65 scope document.

## Visual registry reconciliation

- 10 Customer Company images
- 34 Design System/Restaurant images
- 10 Retail images

Total acceptance set: 54. The filesystem has 55 PNGs because the original Action
Center image is superseded by its v2 and is not counted.

## UAT entry criteria

- Commit and push the exact candidate to `chaiyanutaiagent/restaurant`.
- Capture immutable commit/archive/image identity.
- Back up all five data boundaries, uploads and Redis before migration.
- Deploy only UAT Backend/Frontend and retain Production identities unchanged.
- Run integration, governance, context/permission, state and cross-tenant smoke.
- Rehearse app rollback and restore the WP65 candidate.
- Do not execute QA access cleanup before final Product Owner sign-off.
