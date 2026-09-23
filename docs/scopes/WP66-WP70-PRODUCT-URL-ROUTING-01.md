# WP66–WP70 Product URL Routing

Date: 2026-09-23

Environment: UAT only

Production: **HOLD / unchanged**

## Outcome

Foodchainservice remains one repository, one frontend and one backend. Product
workspaces receive canonical entry URLs while Company/Brand/Branch authorization
continues to come from the signed Server context.

| Workspace | Canonical path | UAT hostname |
|---|---|---|
| Company Admin / shared ERP | `/company` | `uat-app.foodchainservice.com` |
| Restaurant POS | `/restaurant` and `/restaurant/pos` | `uat-restaurant.foodchainservice.com` |
| Retail POS | `/retail` and `/retail/pos` | `uat-retail.foodchainservice.com` |
| Takeaway POS | `/takeaway` and `/takeaway/store/orders` | `uat-takeaway.foodchainservice.com` |

The legacy `/pos` and `/pos/offline-sync` paths remain compatibility redirects
that choose the canonical path from the signed `business_type`. They do not
accept a client-provided business type.

## Security boundary

- Product routes require `business_type` and `target_database` to match.
- A mismatched session may switch only to a branch returned by
  `GET /system/me/branches` and then receives a new signed token from
  `POST /auth/switch-branch`.
- One matching branch is selected automatically; multiple matching branches
  require an explicit choice; zero matches fail closed.
- Editing a route or hostname does not grant access to another product.
- Query caches are cleared after context switching. Existing POS catalog and
  offline queues retain Company/Brand/Branch/business isolation keys.
- UAT automatic login accepts only exact configured `uat-*.foodchainservice.com`
  hostnames. Wildcards, URLs and Production hostnames are rejected.

## Local gate

- Frontend TypeScript: PASS.
- Frontend production build: PASS; existing non-blocking chunk-size warning.
- Backend UAT host allowlist: 10/10 tests PASS.
- Retail canonical route desktop/tablet E2E: 1/1 PASS.
- Full WP65 regression and physical-device suites were not repeated because the
  change is routing/context-scoped and the Product Owner requested a bounded gate.

## UAT activation

1. Build immutable Backend and Frontend images from the committed source.
2. Add the four exact UAT hosts to `UAT_AUTH_BYPASS_HOSTS`.
3. Route the four Cloudflare Public Hostnames to the existing UAT Nginx service.
4. Smoke only `/`, the canonical product entry, automatic login, signed context,
   health and readiness for each hostname.
5. Retain the previous UAT images and `uat-pos.foodchainservice.com` as rollback.

## Deferred by design

- Production DNS, Production deployment and Production authentication changes.
- Shared Production SSO across subdomains; UAT uses bounded automatic login.
- Takeaway/Central Kitchen/Distribution transaction activation.
- Retail Production data-source cutover.
- Printer, cash drawer, PromptPay, camera/touch and network-interruption UAT.
