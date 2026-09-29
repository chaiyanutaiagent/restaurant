# Takeaway Store UAT 1.1.0-uat.6 — Superadmin session fix

Date: 2026-09-29  
Status: **DEPLOYED TO UAT / DEVICE CONFIRMATION PENDING**  
Source commit: `9d8bde29562ce2f0edce0ce3d25573dff52884cf`

## Cause and correction

The UAT API authenticated `superadmin`, listed branch `BKK-01` and returned the
Store login response with HTTP 200. The `uat.5` client then rejected the local
session solely because the returned User record was marked `is_superuser=true`.

`uat.6` trusts the signed Store-session boundary instead of the tenant identity
flag. The client still requires the Takeaway Store surface, Company, Branch,
Brand, station and device claims; it still rejects wildcard permissions. The
backend continues to reduce the temporary UAT superadmin to the 12 allowlisted
Store permissions.

## Published artifact

- Package: `com.foodchainservice.takeaway.uat`
- Version: `1.1.0-uat.6` / `10105`
- APK: `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/foodchainservice-takeaway-store-1.1.0-uat.6.apk`
- Manifest: `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/latest.json`
- APK SHA-256: `b125db2e68db4c48fd9c7e1b752310ffa85bd58729d41ddb7773b73bd8e2eb7a`
- Minimum supported version: `10105`; installed `uat.5` clients are required to
  update before continuing.
- Rollback version: `10104`; the previous manifest is preserved as
  `latest-uat.5.json` on the UAT host.

## Verification

- TypeScript: PASS.
- Dedicated Store bundle boundary: PASS, 6 compiled files.
- Mobile Store Playwright: PASS, 9/9 including restricted-superadmin acceptance
  and wildcard rejection.
- Android package: PASS, `com.foodchainservice.takeaway.uat`.
- Android version: PASS, `1.1.0-uat.6` / `10105`.
- Public manifest signature and downloaded APK hash: PASS.
- Manifest response: HTTP 200, JSON, CORS `*`, cache disabled.
- Production was not changed.
