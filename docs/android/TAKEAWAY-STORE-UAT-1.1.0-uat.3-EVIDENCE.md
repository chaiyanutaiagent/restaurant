# Mobile Store implementation gate — 2026-09-29

Status: **IMPLEMENTATION_GATE_PASS**. This is not a deployment or physical-UAT approval.

Source branch: `codex/foodchainservice-platform`. Parent: `cebeba1`.
The Mobile Store commit containing this document is the handoff unit; use its SHA from Git history. Do not deploy this branch wholesale: its existing Stripe work remains under CTO NO-GO. QA must cherry-pick this commit onto a release branch based on the approved UAT baseline, review dependency differences and verify that release separately.

## Review and corrections

- Separate Vite entrypoint, exact frontend routes and subset API adapter; compiled bundle has no Restaurant/Retail/Platform/Central/Admin routes.
- Business-code resolution, credentials, branch selection and station/device UUID are explicit; no fixed company or admin auto-login.
- Signed `takeaway_store` claims survive refresh. Backend checks live role grants, allowed method/path and signed company/branch/device headers. Superusers and central-kitchen-only roles cannot log in to Store.
- Store stock and transfer receiving validate destination company/branch/location before processing; received stock audit carries the Store branch.
- Dedicated offline database; company/brand/branch/user-scoped reads and reprints; tenant-qualified sale IDs; unsynced records prevent logout cleanup. Native credentials use secure storage, not the old admin localStorage.
- Fixed stale-response and failed-refresh races so an old user's request cannot overwrite or clear a newly selected employee/company session.
- Limited mobile session-expiry decoding to the mobile store, preserving the existing web authentication path.
- Disabled the legacy full-app update channel in the Store bundle. Candidate installation is manual; no remote manifest or APK hosting was changed.
- Production assembly is blocked. The actual Android embedded assets are scanned before build, then the finished APK is independently scanned.
- No database provisioning, live transactions, UAT/Production deployment, ERP-POS access, remote changes or unrelated file staging was performed.

## Executed checks

| Gate | Result |
| --- | --- |
| Backend full unittest discovery | PASS: 609 run, 608 passed, 1 skipped |
| Focused `test_mobile_store_boundary.py` | PASS: 8/8 |
| Role preparation CLI import + permission seed SQL compilation | PASS; no database writes |
| `npm run type-check` | PASS |
| Full web `npm run build` | PASS |
| `npm run build:android:uat` | PASS; separate Store bundle + Capacitor sync |
| Dedicated bundle checker | PASS: 6 compiled files |
| Playwright mobile-store | PASS: 7/7; no retries |
| Android `testDebugUnitTest lintDebug assembleDebug` | BUILD SUCCESSFUL |
| Native app unit test | PASS: 1 existing ExampleUnitTest; explicitly rerun, not hardware coverage |
| App lint | PASS: 0 errors, 13 warnings |
| Finished APK checker | PASS: 8 embedded JS/HTML assets |
| APK signature | PASS: v1 + v2, one Android Debug RSA-2048 signer |
| Git whitespace check | PASS |

The skipped backend test requires `RETAIL_DATABASE_URL`; it is an existing shared-reporting integration test, not a mobile-boundary skip. Full regression logs contain expected mocked network-failure output, deprecation notices and a local test JWT-key-length warning; no server configuration or secrets were changed. Vite reports large-chunk warnings. Native unit coverage is only the existing smoke unit test. Browser tests use mocked API responses and the secure-storage web fallback; backend boundary tests use signed JWTs and mocked database queries. These do not replace live two-company or hardware UAT.

## Candidate artifact

- Name: Foodchainservice Takeaway Store UAT
- Package: `com.foodchainservice.takeaway.uat`
- Version: `1.1.0-uat.3` / versionCode `10102`
- minSDK 23 / targetSDK 35
- Build output: `/Users/user/Projects/restaurant/frontend/android/app/build/outputs/apk/debug/app-debug.apk`
- QA copy: `/private/tmp/foodchainservice-takeaway-store-1.1.0-uat.3-10102.apk`
- APK SHA-256: `daa7ff5993b1632650040cf284d10171f179b2ca6338d8d8bfa26f91dbc169a9`
- Signing certificate SHA-256: `acfe7c0638c1375ce6c041d53f99edac9467dfec64f7297ee07f3436704015b5`

The artifact is local and debug-signed. It has not been published to a download server, installed on a physical device or approved for customers. APK scan checks absence of `/restaurant`, `/retail`, `/platform`, `/takeaway/central`, `/takeaway/admin`, the old auto-login endpoint, old tenant UUID and business slug. Source/config review verifies no replacement hard-coded tenant is introduced.

## Upgrade / rollback evidence

Preserved uat.2 reference: `/private/tmp/foodchainservice-takeaway-1.1.0-uat.2-download-test.apk`.
SHA-256: `06fccc9e8f8bb182ecf12479aa096552c31d87f240d44dbcf9255b2331e213a1`.
Its signing certificate matches this candidate; this supports an Android in-place upgrade, but the certificate of the actual installed APK must still be checked. Sync old transactions first. The old admin session and old outbox are not imported. Never uninstall or clear data with unresolved sales. uat.2 remains Internal Admin UAT / rollback reference only, not a customer Store release.

## Remaining release blockers (outside implementation gate)

1. QA must isolate this commit from NO-GO Stripe changes and obtain approval before any UAT deployment.
2. Matching backend endpoints, role preparation and branch/station assignments must exist on the approved UAT release. Earlier read-only readiness returned 404 for the mobile onboarding endpoint; no new server changes were attempted in this gate.
3. Verify UAT CORS for the native HTTPS origin and a separate second company's accounts. Device UUID binding is session-context binding, not hardware attestation or managed-device enrollment.
4. Physical Android upgrade, secure-storage restart, QR camera, printer, cash, offline reconnect and live two-company permission testing remain pending.
5. Rebuild the APK from the isolated release branch and compare/re-record its checksum before external distribution; the candidate here was built from the implementation branch.

See `TAKEAWAY-STORE-UAT-1.1.0-uat.3.md` for persona matrix, build commands and safe install/rollback procedure.
