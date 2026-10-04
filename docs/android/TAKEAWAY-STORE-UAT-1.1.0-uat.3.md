# Foodchainservice Takeaway Store UAT 1.1.0-uat.3

Date: 2026-09-29. Package: `com.foodchainservice.takeaway.uat`. VersionCode: `10102`.

## Release classification

- `1.1.0-uat.2` / 10101 is **Internal Admin UAT / rollback reference only**. It embeds a tenant and admin auto-login; it is not a store release and must not be distributed to customer store employees.
- `1.1.0-uat.3` is the dedicated multi-company Store candidate. Production builds and real-money activation remain on HOLD. The Android release task explicitly refuses production assembly.
- Only repository `chaiyanutaiagent/restaurant` is modified. ERP-POS is not accessed during final review/implementation gate.
- No UAT or Production deployment is authorized. This branch contains unrelated Stripe work under NO-GO; QA must cherry-pick only the Mobile Store commit onto a safe UAT-baseline release branch, review and test it there before any deployment.
- The legacy in-app update feed is disabled in the dedicated Store bundle. QA distributes this candidate manually until a Store-specific signed channel is approved; no remote manifest is changed.

## Implementation plan and file map

| Work | Implementation | Acceptance |
| --- | --- | --- |
| P0 classification | This document | uat.2 explicitly marked Internal Admin; no production release |
| P1 store bundle | `frontend/vite.mobile-store.config.ts`, `src/mobile-store/main.tsx`, `routes.ts`, `takeawayApi.ts` | Separate entrypoint; seven exact routes; manual forbidden URL denied; forbidden modules absent from compiled APK |
| P2 onboarding | `backend/app/routers/mobile_store_auth.py`, `frontend/src/mobile-store/Onboarding.tsx`, `session.ts`, `api.ts` | Business Code or QR, employee credentials, assigned Takeaway branch, station and installation UUID; no default company or auto-login |
| P3 server boundary | `backend/app/services/mobile_store_policy.py`, `auth_service.py`, `dependencies.py`, `utils/security.py` | Signed store surface survives refresh; backend allowlist; company/branch/device header binding; live permission recalculation; superusers denied |
| P3 personas | `role_preset_service.py`, `seed_permissions.py`, `cli/prepare_sketch_biz_test_staff.py` | Cashier, branch manager, receiving, central kitchen, company owner; explicit `takeaway.store.access`; central kitchen denied mobile |
| P3 stock/receiving | `routers/takeaway.py`, `services/takeaway_service.py` | Store transfer listing and receiving limited to destination branch; stock writes validate store location and catalog tenant |
| P4 isolation | `frontend/src/mobile-store/db.ts`, `lib/takeawayOffline.ts` | Dedicated database, company/brand/branch/user-scoped reads, tenant-qualified sale IDs, no cross-scope reprint, logout blocks unsynced rows |
| P4 tests | `backend/tests/test_mobile_store_boundary.py`, `frontend/e2e/mobile-store.spec.ts`, `scripts/check-mobile-store-{bundle,apk}.mjs` | API/URL deny, role deny, two-company context and offline isolation, logout cleanup, unknown/inactive business, no forbidden compiled paths |
| P5 candidate | `frontend/android/app/build.gradle`, debug manifest/resources | 10102 / uat.3; encrypted native credential storage; camera permission; HTTPS only; Gradle verifies embedded Store assets |

## Store access matrix

| Persona | Sell/prepare | Shifts | Store stock | Order/receive | Credit | Mobile login |
| --- | --- | --- | --- | --- | --- | --- |
| Takeaway Cashier | Yes | Yes | Read | Central orders | No | Assigned branch/station |
| Takeaway Branch Manager | Yes | Yes | Read/adjust | Yes | View/request payment verification | Assigned branch |
| Takeaway Stock / Receiving | No | No | Read | Yes | No | Assigned branch |
| Central Kitchen | No mobile | No mobile | Web central workspace | Web central workspace | No mobile | Denied |
| Company Owner | Yes | Yes | Read/adjust | Yes | View/request | Reduced to selected Takeaway branch |
| Superadmin | No | No | No | No | No | Denied; use Platform |

No mobile route exposes Restaurant, Retail, Platform, Takeaway Central/Admin, role editing, credit approval, credit-limit changes, refunds or database import. `takeaway.store.access` is an explicit grant, not an inferred permission from stock visibility. Existing web role grants remain effective on web; the Store session caps them independently.

QR content is a Business Code (for example, a company's assigned slug) or `foodchainservice://business/<code>`. It is data only and never an arbitrary navigation URL. Unknown/inactive codes fail closed. Employees must authenticate again to select another company. Passwords are never saved. Native tokens, tenant context and device identity use Android secure storage. Browser tests use the plugin's browser implementation; they do not prove Android keystore/hardware behavior.

Offline records remain on this device only and are filtered by company, brand, branch and user. Logout requires pending/syncing/review rows to be resolved, then clears synced sales, cached workspace and credentials. Sequences are retained to prevent ID reuse. Session expiry/role revocation is enforced by the server; offline sales are limited to the current signed session lifetime. Upgrade does not import the old admin token or old application's cached transaction database. Sync all old queued work before upgrading.

## UAT dependencies and risks (future release approval required)

1. The candidate requires the matching backend commit. Read-only check on 2026-09-29: `GET /api/v1/mobile-store/businesses/sketch-biz` on the UAT Takeaway hostname returned HTTP 404; this route is not deployed there yet.
2. After QA isolates the Mobile Store commit onto a safe UAT-baseline release branch and obtains deployment approval, deploy that release (not this entire branch). Preview `python -m app.cli.prepare_mobile_store_roles --company-id <company-uuid>` and apply with `--apply` only after approval. This prepares four Store/Central roles and adds Store access to an existing Company Owner/Takeaway Store Operator role; it does not create users, reset passwords or reseed business transactions. Assign employees to the correct Takeaway branch/station using the existing staff administration flow. Existing permissions alone do not grant mobile access. No schema migration is added by this change.
3. For Sketch Biz, the existing UAT preparation scripts now include four additional synthetic personas (`test.chambo.store-cashier`, `test.chambo.store-manager`, `test.chambo.store-receiving`, `test.chambo.central-kitchen`). The existing `test.owner` covers owner. Preparation scripts are not executed as part of APK packaging; use their UAT checks and existing secret injection when provisioning.
4. A second independent UAT company with its own staff and branch is required for the live cross-company check. Browser and backend boundary tests use synthetic fixtures, not live customer credentials.
5. UAT must allow CORS for the Capacitor HTTPS origin and `X-Store-Device-ID`. Existing backend allows all request headers; verify the configured origins at deployment.
6. Camera, secure storage restart, Bluetooth printer and Android upgrade/back navigation remain physical UAT items. The app is a debug-signed UAT candidate, not a production-signed distribution.

## Build and verification

```sh
npm --prefix frontend run type-check
npm --prefix frontend run build
npm --prefix frontend run build:android:uat
node scripts/check-mobile-store-bundle.mjs frontend/dist-mobile-store
cd frontend/android
./gradlew testDebugUnitTest lintDebug assembleDebug
```

Use JDK 21 and Android SDK 35. The Store config refuses auto-login=true, default Company/Business Slug, non-UAT host, or a different mode. Gradle independently checks the actual embedded assets before assembly; copying the full web app into Android cannot pass.

Backend regression must run with the repository root available because several existing tests inspect frontend files:

```sh
docker compose run --rm --no-deps -e PYTHONPATH=/workspace/backend \
  -v /Users/user/Projects/restaurant:/workspace:ro -w /workspace/backend \
  backend python -B -m unittest discover -s tests -p 'test_*.py'
cd frontend
npx playwright test --config=playwright.mobile-store.config.ts
```

## Install / upgrade / rollback

1. Sync every queued transaction in uat.2 and record the old package version and signing certificate. Do not clear data or uninstall while anything remains unsynced.
2. Compare the supplied SHA-256 and APK signing-certificate SHA-256. Install with `adb install -r <uat.3.apk>` only when the old installed package has the same certificate.
3. If signatures differ, Android will reject the upgrade. Use a separate QA device or obtain an APK signed with the existing UAT key. Do not uninstall a device containing unresolved transactions merely to bypass this check.
4. First launch shows Business Code; enter/scan the company, authenticate an employee, choose the permitted branch and confirm station. No old admin session is accepted.
5. Verify each persona and test manual forbidden routes, company switching, offline reconnect, receipt/transfer/credit requests, scanner and printer.
6. Rollback uses the preserved uat.2 artifact on an internal test device only. Downgrade can require `adb install -r -d` and a compatible signature; preserve data/backup first. uat.2 restores its admin-risk surface and is never a substitute customer Store release. Prefer rolling backend forward or holding Store rollout.

## Evidence / gate

Final evidence, artifact SHA-256, signing certificate, commit and deployment gate are recorded in the adjacent release evidence file. A local candidate alone is not approval to start physical UAT against an incompatible server.
