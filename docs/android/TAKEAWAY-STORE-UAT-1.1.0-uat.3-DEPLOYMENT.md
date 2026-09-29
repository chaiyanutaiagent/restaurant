# Takeaway Store UAT 1.1.0-uat.3 deployment evidence

Date: 2026-09-29  
Environment: UAT only  
Software gate: **PASS**  
Physical-device gate: **PENDING**

## Release identity

- Approved UAT source commit: `60fd4d9b6ffb58593edd87540b87ea369b064c44`
- Isolated implementation commit: `5d5f5f3fc9781672491d93e84e077e4870313bbc`
- Backend image: `restaurant-pos-backend:uat-mobile-store-60fd4d9`
- Frontend image: `restaurant-pos-frontend:uat-mobile-store-60fd4d9`
- APK package: `com.foodchainservice.takeaway.uat`
- APK version: `1.1.0-uat.3` / versionCode `10102`
- APK SHA-256: `d50062c0ae0447b99e3d9d8a99fe0d61de1c073e7df73b8b611e68cc8e967781`
- Signing certificate SHA-256: `acfe7c0638c1375ce6c041d53f99edac9467dfec64f7297ee07f3436704015b5`
- Download: `https://uat-takeaway.foodchainservice.com/downloads/foodchainservice-takeaway-store-1.1.0-uat.3.apk`

The UAT candidate was rebuilt from the isolated UAT release branch. The old `uat.2` APK remains available only as a rollback artifact. Production was not changed.

## Pre-deployment verification

- Backend regression: 594 passed, 1 existing integration test skipped.
- Frontend type-check and production build: PASS.
- Dedicated Mobile Store bundle build and forbidden-route scan: PASS.
- Playwright Mobile Store: 7/7 passed.
- Android unit, lint and debug assembly: PASS.
- Finished APK embedded-asset scan: PASS.
- APK signatures: v1 and v2 verified; same debug certificate as `uat.2`.
- Git remote verified as `chaiyanutaiagent/restaurant`; release branch pushed before deployment.

## Deployment and rollback

- Release directory: `/home/behappyaiagent/restaurant-uat-releases/60fd4d9`
- Pre-deployment database/config backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/mobile-store-before-60fd4d9-20260929`
- Post-deployment backend health: healthy.
- UAT POS, App, Restaurant, Retail and Takeaway roots: HTTP 200.
- Both Store business-code onboarding endpoints: HTTP 200.
- Public APK download: HTTP 200 and SHA-256 matched the local candidate.
- QA mode and legacy bypass were restored to their pre-test values after the bounded isolation check.

## Live UAT boundary evidence

Sketch Biz Store test:

- Store cashier branch discovery and login: HTTP 200.
- Allowed Store API: HTTP 200.
- Admin API and wrong device binding: HTTP 403.
- Central-kitchen-only role: HTTP 403.
- Unknown business code: HTTP 404.

Two-company Store test (`sketch-biz` and synthetic `qa-isolation-beta-uat`):

- Separate companies and branches: verified.
- Own Store status and own catalog: HTTP 200 for both.
- Cross-company header spoof: HTTP 403 in both directions.
- Admin API: HTTP 403 for both Store sessions.
- No password, access token or refresh token was emitted in evidence.

The generic signed tenant isolation fixture also returned HTTP 200 for each tenant's own resource, HTTP 404 for both cross-tenant resource reads, and ignored spoofed company headers.

## Runtime observation

The backend process had one native `libpython3.11` exit-139 event after the fixture/projection workload. Docker restarted it automatically. It returned healthy with no OOM and no Python traceback. A repeat two-company Mobile Store smoke followed by a 45-second observation passed with the restart count unchanged. Keep this isolated event under UAT monitoring; it is not approved for Production.

## Remaining physical UAT

1. Install or upgrade the APK on the Android tablet without clearing unsynced `uat.2` data.
2. Verify Business Code/QR camera, secure session after app restart, and Android back navigation.
3. Verify Bluetooth receipt printing and cash-drawer opening for cash only.
4. Verify non-cash payment prints a receipt without opening the drawer.
5. Verify offline sale, app restart, reconnect/sync, reprint isolation and long receipt behavior.

Production release remains on HOLD until these physical checks and production signing are complete.
