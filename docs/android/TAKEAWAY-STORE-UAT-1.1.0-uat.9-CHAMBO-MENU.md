# Takeaway Store UAT 1.1.0-uat.9 — Chambo Menu

Deployment date: 2026-10-05 (Asia/Bangkok)

## Scope

- Application release commit: `adaa2fc94c097ee21b865176c5cb3e363b095e9f`
- Branch: `codex/chambo-store-menu-uat9`
- Environment: UAT only
- Android package: `com.foodchainservice.takeaway.uat`
- Version: `1.1.0-uat.9` (`versionCode 10108`)
- Minimum supported version: `10108`
- Rollback version: `10107`

The Store shell now follows the established Chambo navigation: primary tabs for
ขาย, Stock, ปิดกะ, สั่ง/รับสินค้า, and เครดิต; permission-filtered secondary
actions remain in the store drawer. Existing tenant, route, and permission
boundaries remain enforced.

## Verification

- TypeScript check: passed.
- Store release-policy tests: 3 passed.
- Store Playwright regression: 14 passed.
- Store bundle boundary check: passed, 6 compiled files.
- Android unit tests, lint, and debug assembly: passed.
- APK boundary check: passed, 8 packaged assets.
- APK signature schemes: v1 and v2 passed.
- Signing certificate SHA-256:
  `acfe7c0638c1375ce6c041d53f99edac9467dfec64f7297ee07f3436704015b5`

## Publication

- Immutable source directory:
  `/home/behappyaiagent/restaurant-uat-releases/adaa2fc`
- APK:
  `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/foodchainservice-takeaway-store-1.1.0-uat.9.apk`
- Manifest:
  `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/latest.json`
- APK SHA-256:
  `85a5b96e83bc2a278037db3856429365ba1f4433f36f8b9a938189dfe7b482f3`

The signed manifest and APK were downloaded again through the public HTTPS URLs;
signature, package, version, channel, and checksum verification passed. UAT 8 is
retained as `latest-uat.8.json`; UAT 9 is retained as `latest-uat.9.json`.

## Runtime isolation

This was an artifact-only UAT publication. No application container, database,
Redis instance, Nginx instance, or Cloudflare Tunnel was recreated. All public
UAT roots plus `/health` and `/health/ready` returned HTTP 200 after publication.
Every Production container identity remained unchanged.

Rollback is the atomic restoration of the retained UAT 8 manifest. No database
restore is required because this release contains no backend, schema, or data
change.

## Physical acceptance

Open an installed UAT 8 app on the Redmi device, confirm the mandatory UAT 9
update prompt and Android installation flow, relaunch, sign in, and verify the
five Chambo-style tabs plus the permission-filtered drawer.
