# WP64 — Public Customer Experience

Date: 2026-09-22

Environment: Local and UAT only

Production: **NO-GO / unchanged**

## Objective

Make every currently exposed customer-facing surface honest about what the
Server can do. The Company storefront remains a public Catalog and Branch
Locator. Existing Restaurant table QR and Quick-service ordering remain on
their approved Server-priced contracts. Takeaway ordering remains under the
WP62 dark-launch write gate.

## Product decision applied

The Owner has not approved Ecommerce Option B. WP64 therefore applies Option
A: **Catalog and Branch Locator**.

- Catalog and branch discovery are available.
- No Storefront cart, checkout, payment or customer account is implied.
- The UI no longer presents internal SKU/barcode as customer content.
- Digital receipt, Member portal and Ecommerce remain explicit future gates.

Restaurant QR/Quick-service are separate session-token flows already accepted
in WP49. This decision does not disable those flows and does not expand the
Storefront into Ecommerce.

## Delivered scope

- Server-authoritative `experience` contract on the Storefront summary:
  release stage, freshness, capabilities and hard holds.
- Customer-facing Thai naming and a prominent catalog-only disclosure.
- Loading, Empty, No-results, Error, Offline and Stale handling using the
  shared system-state pattern.
- Server capability panel that shows Catalog/Locator open and
  Order/Payment closed.
- Desktop 1440×900 and Tablet 1024×768 responsive browser coverage.
- Privacy-safe public rate-limit keys; neither client IP nor public token is
  retained directly in the limiter key.
- Rate limiting for Storefront summary/products/branches and all current
  Restaurant table-QR/Quick-service public reads and mutations.
- Existing Restaurant price authority and idempotency remain unchanged:
  `DiningService` recalculates and locks price on the Server and rejects stale
  price evidence.
- Takeaway public routes retain the WP62 token, expiry, rate-limit and
  Server-authoritative transaction HOLD.

## Capability boundary

| Surface | Current result | Boundary |
|---|---|---|
| Public Storefront | Catalog + Branch Locator | No cart, checkout, payment or member account |
| Restaurant Table QR | Existing session-scoped ordering/status | Server price/idempotency and table/session token apply |
| Restaurant Quick-service | Existing token ordering/status | Server price/idempotency and branch token apply |
| Takeaway ordering | Catalog/read-only dark launch | POST remains HTTP 409 while WP62 write flag is false |
| Takeaway pickup status | Purpose-bound token read | No payment credential or PII in URL |
| Digital receipt | HOLD | Secure receipt token contract not implemented |
| Member portal | HOLD | Customer identity/consent/recovery not implemented |
| Ecommerce | HOLD | Owner decision, inventory reservation, checkout/provider and privacy gates required |

## Security and failure behavior

- Business slug and order tokens continue to resolve scope on the Server.
- Public route limiter keys hash the network identity and public subject.
- HTTP 429, unavailable summary or network failure cannot render a false
  Catalog success state.
- Stale data remains visible only with an explicit warning and refresh action.
- Public errors do not include internal stack traces, tokens or customer PII.

## Local acceptance evidence

- Backend WP63/WP64 and Restaurant database-boundary tests: 11/11 passed.
- Public browser tests at Desktop and Tablet: 6/6 passed.
- Existing Platform suite Storefront tenant-routing case passed.
- Frontend TypeScript: passed.
- Frontend production build: passed; the existing large-chunk warning remains.
- Backend and Frontend immutable local images built:
  `restaurant-pos-backend:wp64-local` and
  `restaurant-pos-frontend:wp64-local`.
- Built Backend image loaded 48 route groups.

The stale Platform fixtures found during the first broad run were corrected
against the current Company Foundation contracts. The final Platform browser
suite passed 20/20, including Company routing, cross-Tenant rejection,
Platform Auditor read-only controls and surface-specific QA banners.

## Explicit exclusions

- No Ecommerce, pickup slot, payment session or provider callback.
- No Digital receipt or real tax-document link.
- No customer identity, loyalty/member account or consent center.
- No Takeaway, Central Kitchen or Distribution transaction activation.
- No real provider, real tax, Retail data-source change or Production flag.
- No Production deployment.

## UAT checkpoint

Combined Batch C software UAT passed on commit `f753bd3`. The UAT Storefront
reported `catalog_locator` with checkout disabled; Restaurant QR menu/status
remained healthy; Takeaway, Kitchen and Distribution write gates returned
HTTP 409; signed Tenant A/B isolation and Auditor least privilege passed; and
app-only rollback/restoration completed without replacing stateful UAT
containers. Production was not changed.

WP65 may begin on Local/UAT. Physical devices, real providers/tax documents,
real Chambo data, transactional Takeaway/Supply-chain activation and
Production remain HOLD.
