# Takeaway Store UAT 1.1.0-uat.4 — signed update channel

Date: 2026-09-29  
Status: **DEPLOYED TO UAT / PHYSICAL UPGRADE TEST PENDING**  
Source commit: `2a9d19933aa6171e453888605561518a85e9a56a`

## Outcome

- The Android Store app checks its dedicated UAT release manifest when it opens, when connectivity returns and every six hours while it remains open.
- A newer signed release displays an update gate. Optional releases can be deferred; a version below `minimum_supported_version_code` is blocked until update.
- The native updater allows only Foodchainservice HTTPS hosts and verifies manifest signature, APK SHA-256, package id, version code and APK signer before opening Android Package Installer.
- The update is an in-place install. The company session, secure credentials, offline queue and printer configuration are not cleared.
- Android still requires the user to authorize `Install unknown apps` once and confirm each installation. Silent installation requires managed-device/MDM ownership and is outside this sideloaded UAT channel.
- `uat.2` and `uat.3` cannot discover this channel because they were built without the Store updater. They require one manual in-place installation of `uat.4`; later releases can be discovered from inside the app.

## Published UAT artifact

- Package: `com.foodchainservice.takeaway.uat`
- Version: `1.1.0-uat.4` / `10103`
- APK: `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/foodchainservice-takeaway-store-1.1.0-uat.4.apk`
- Manifest: `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/latest.json`
- APK SHA-256: `f56fc8330242e7d60099df7a2f04f131b38f85fe29dd37f7e9c820fd3bc35c1e`
- Android signing certificate SHA-256: `acfe7c0638c1375ce6c041d53f99edac9467dfec64f7297ee07f3436704015b5`
- Manifest signing key: Ed25519; private key remains only in the ignored local `.secrets` directory and was not uploaded to the UAT host.

## Verification performed

| Check | Result |
| --- | --- |
| TypeScript | PASS |
| Mobile Store Playwright | PASS: 8/8, including valid and tampered Ed25519 manifests |
| Store bundle boundary | PASS: 6 compiled files |
| Android unit, lint, assemble | PASS |
| Finished APK boundary | PASS: 8 embedded assets |
| APK package/version | PASS: `com.foodchainservice.takeaway.uat`, `1.1.0-uat.4`, `10103` |
| APK signatures | PASS: v1 and v2; same debug signer as `uat.2`/`uat.3` |
| Published manifest signature + downloaded APK hash | PASS |
| Manifest CORS/cache policy | PASS: `Access-Control-Allow-Origin: *`, `no-store` |
| Five public UAT roots | PASS: HTTP 200 |
| UAT containers after frontend replacement | PASS: backend healthy; frontend, nginx, postgres, redis and cloudflared running |

## UAT deployment boundary

- Frontend image: `restaurant-pos-frontend:uat-store-updater-2a9d199`
- Backend remains: `restaurant-pos-backend:uat-mobile-store-60fd4d9`
- Android download directory remains a read-only mount inside the frontend container.
- No database migration or data mutation was performed.
- Production was not changed.

## Remaining physical proof

1. Install `uat.4` over the currently installed UAT package without uninstalling it.
2. Confirm login/session, pending offline records and printer pairing remain intact.
3. Publish a higher test build and verify app-open detection, one-time unknown-app permission, download validation and Android confirmation.
4. Relaunch and confirm the installed version no longer shows the update gate.
