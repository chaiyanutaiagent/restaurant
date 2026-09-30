# Takeaway Store UAT 1.1.0-uat.7 — Product Catalog

Deployment date: 2026-09-30 (Asia/Bangkok)

## Scope

- Release commit: `25fea8a36b9fa0a68774922f7fc742b4eef37b3d`
- Branch: `codex/takeaway-product-experience`
- Environment: UAT only
- Android package: `com.foodchainservice.takeaway.uat`
- Version: `1.1.0-uat.7` (`versionCode 10106`)
- Minimum supported version: `10106`
- Rollback version: `10105`

The release adds the Takeaway product-catalog experience for Store and Admin: product photo, description, SKU/barcode, category, unit, price, stock-backed availability, featured status, display order, search, and external scanner workflow. Public ordering shows only customer-facing availability and does not expose internal stock quantities.

## Change controls

- UAT pre-deploy backup:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/product-catalog-before-4ea36e9-20260929T152849Z`
- Release directory:
  `/home/behappyaiagent/restaurant-uat-releases/25fea8a`
- Only the `backend` and `frontend` services were replaced.
- PostgreSQL, Redis, nginx, and cloudflared were preserved.
- Production was not changed.

## Deployed images and migration

- Backend: `restaurant-pos-backend:uat-product-catalog-25fea8a`
- Frontend: `restaurant-pos-frontend:uat-product-catalog-25fea8a`
- Takeaway database head: `p6takeaway0009`
- Added columns: `description`, `image_url`, `sort_order`, `is_featured`

## Verification evidence

- Backend regression: 599 passed
- Schema tests: 12 passed
- Store Playwright: 11 passed
- Takeaway Playwright: 6 passed
- TypeScript check: passed
- Frontend build: passed
- Android test/lint/assemble: passed
- APK boundary checks: passed
- APK v1/v2 signature: passed
- Five public UAT roots: HTTP 200
- Backend health: healthy, restart count 0
- Frontend restart count: 0
- Post-deploy backend error scan: 0 matching critical errors
- Signed Store authorization/catalog smoke: passed
  - Branch: `BKK-01`
  - Catalog rows: 46
  - Stock-available rows: 38
  - Mutation count: 0

The automated Store smoke signs an isolated, short-lived Store token inside UAT. It validates the deployed authorization boundary and product API without printing credentials or tokens and without mutating operational data.

## APK publication

- Manifest:
  `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/latest.json`
- APK:
  `https://uat-takeaway.foodchainservice.com/downloads/takeaway-store/foodchainservice-takeaway-store-1.1.0-uat.7.apk`
- APK SHA-256:
  `a9e9c500105fce3db9cd42ed0f1cf64a9df216a0d08a446e14a8899e1e6c8c6f`
- Signing certificate SHA-256:
  `acfe7c0638c1375ce6c041d53f99edac9467dfec64f7297ee07f3436704015b5`
- Published manifest signature: verified
- APK downloaded back from the public URL: checksum verified

## Remaining physical UAT

This release is ready for controlled device testing. Final acceptance still requires a real Android device test for update prompt/install, login with the user-managed superadmin password, product image rendering, barcode scanner input, sale flow, receipt printer, and cash drawer behavior. Those physical checks are not certified by this deployment record.
