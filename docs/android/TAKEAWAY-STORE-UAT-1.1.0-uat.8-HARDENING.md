# Takeaway Store UAT 1.1.0-uat.8 — Production Guards

Deployment date: 2026-09-30 (Asia/Bangkok)

## Scope

- Application release commit: `18928aa24c601d33071f21e9bdfd06b2752bee29`
- Branch: `codex/takeaway-store-production-guards`
- Environment: UAT only
- Android package: `com.foodchainservice.takeaway.uat`
- Version: `1.1.0-uat.8` (`versionCode 10107`)
- Minimum supported version: `10107`
- Rollback version: `10106`

This release hardens the Store test-access boundary, mobile-session tenant binding,
signed release policy, Android package/signer/version verification, and the
multi-company release and rollback operating model. Production was not changed.

## Change controls

- Pre-deployment backup:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/takeaway-store-before-18928aa`
- Backup validation: all five PostgreSQL custom-format dumps passed
  `pg_restore --list`; uploaded files were archived; SHA-256 verification passed.
- Immutable release directory:
  `/home/behappyaiagent/restaurant-uat-releases/18928aa`
- Backend image: `restaurant-pos-backend:uat-store-hardening-18928aa`
- Frontend image: `restaurant-pos-frontend:uat-store-hardening-18928aa`
- Only `backend` and `frontend` were replaced.
- PostgreSQL, Redis, nginx, and cloudflared container identities were preserved.
- Database migration trees were unchanged from the previous UAT release.
- Rollback runbook: `docs/android/TAKEAWAY-STORE-RELEASE-ROLLBACK-RUNBOOK.md`

## Pre-deployment verification

- Focused backend security regression: 24 passed.
- Full backend regression: 612 passed, 1 expected Retail database skip.
- Release-policy tests: 3 passed.
- TypeScript check: passed.
- Store Playwright: 13 passed.
- Store bundle boundary check: passed, 6 compiled files.
- Android unit tests: 5 passed.
- Android lint and debug assembly: passed.
- APK boundary check: passed, 8 assets.
- APK signature schemes: v1 and v2 passed.
- Signing certificate SHA-256:
  `acfe7c0638c1375ce6c041d53f99edac9467dfec64f7297ee07f3436704015b5`

## Runtime verification

- Five public UAT roots returned HTTP 200.
- `/health` and `/health/ready` returned HTTP 200.
- Backend was healthy; backend and frontend restart counts were zero.
- Post-deploy critical backend error scan returned zero matches.
- Exact approved UAT host auto-login returned HTTP 200.
- A suffix-confusion host returned HTTP 404.
- Signed, two-minute Store catalog smoke passed for branch `BKK-01`:
  - catalog rows: 46
  - available rows: 38
  - out-of-surface system endpoint: HTTP 403
  - mutation count: 0

## APK publication

- Manifest:
  `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/latest.json`
- APK:
  `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/foodchainservice-takeaway-store-1.1.0-uat.8.apk`
- APK SHA-256:
  `35f4507d178806626a79e8bb825cd076a18a91f5cf150aac70aa0f618a3af4fd`
- The manifest was published atomically after runtime checks passed.
- The public manifest signature was verified with the release public key.
- The APK was downloaded back through the public URL and its checksum matched.
- UAT 7 remains available as `latest-uat.7.json` and rollback version `10106`.

## Remaining physical UAT

The automated deployment gate is complete. Final acceptance still requires opening
an installed UAT 7 app on a real Android device, confirming the mandatory UAT 8
update flow and Android installation prompt, then logging in and checking product
images, scanner input, one sale, receipt printing, and cash-drawer behavior. Android
may still require the user to approve installation from the app depending on device
policy; this release does not bypass Android security controls.
