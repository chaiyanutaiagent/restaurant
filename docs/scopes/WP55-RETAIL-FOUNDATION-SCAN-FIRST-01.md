# WP55 — Retail Foundation and Scan-first Sale

Date: 2026-09-22  
Environment: Local and UAT only  
Design coverage: Retail R01–R02  
Production: unchanged and not authorized

## Scope delta

WP55 separates `/pos` by the Server-signed business context. A `retail_pos` session now receives a Retail-only shell, navigation and Catalog contract while Restaurant and Takeaway keep their existing surfaces.

## Implemented

- Added `retail_sale` Catalog scope that requires signed Company, Brand, Branch, `business_type=retail_pos` and `target_database=retail_pos`.
- Retail Catalog is Brand-specific, saleable, active and excludes `menu_item` and `raw_material` even if the Client sends conflicting filters.
- Added Company/Brand/Branch/business-type Catalog cache identity. A cache from another context is hidden and checkout fails closed.
- Added Retail-only navigation: Sale, Hold, Bill/Return, Shift and Device Status. Table, QR, Takeaway, Delivery, KDS and Kitchen do not appear.
- Added Scan/Search focus, barcode/SKU lookup, category/product workspace, touch-sized actions, Pilot/Legacy disclosure, loading/empty/error/offline/permission states and a 64 px primary checkout.
- Retail checkout remains online-only until a signed Retail offline-sale policy exists.
- Server pricing, permissions, stock checks and idempotency remain authoritative at checkout.

## Regression hardening found by parallel QA

QA found two Restaurant Catalog regressions on immutable WP54 candidate `525163f`:

1. Staff Takeaway route showed zero items because the unqualified endpoint ignored the signed Restaurant Brand.
2. Public Table QR returned menu items and categories across other UAT fixture Brands in the same test Company.

WP55 fixes both without changing data:

- Staff WAP resolves and enforces the signed Restaurant Brand.
- Public QR resolves exactly one active Restaurant Brand for the session Branch and fails closed on ambiguity.
- Public products are Brand-scoped; categories are limited to the returned products and duplicate labels are removed.
- Order pricing uses the same uniquely resolved Restaurant Brand, preventing a direct request from bypassing the UI filter.
- Added the missing accessible description to the Device Status dialog found by QA.
- Fixed the Docker fallback regression runner to mount both backend and frontend contract sources.

## Deferred to later Retail packages

- R03–R05 product exception detail, customer/discount and payment/receipt: WP56.
- R06–R08 Hold, Return/Exchange/Void and full Shift Operations: WP57.
- R09–R10 offline recovery and Counter readiness: WP58.
- Retail Production data-source cutover, live provider, real tax and physical hardware acceptance remain prohibited.

## Local checkpoint

| Check | Result |
|---|---|
| Retail/Restaurant Catalog, QR, accessibility and runner regression tests | 17 passed |
| Frontend targeted type-check | Passed |
| Schema/migration change | None |
| Production flags/data source | Unchanged |

## UAT acceptance

- Retail test account enters `/pos` with signed Retail Brand/Branch/Counter context.
- Retail shell shows only Retail navigation and exactly the Brand-scoped Retail test Catalog.
- Barcode `8850000000001` resolves only the Retail UAT product and returns focus to Scan/Search.
- Restaurant main POS remains at 28 items.
- Restaurant Takeaway returns the same signed 28-item menu.
- Public Table QR returns only the 28 Brand items and six unique product categories (plus `ทั้งหมด` in UI).
- No order/payment is required for this checkpoint; mutation testing remains controlled by later WPs and QA scope.
