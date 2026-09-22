# WP64 Local Checkpoint — Public Customer Experience

Date: 2026-09-22

Decision: **LOCAL ENGINEERING GATE PASS / COMBINED BATCH C SOFTWARE UAT PASS**

Production decision: **NO-GO / unchanged**

## Result

The public Company Storefront is now explicitly a Catalog and Branch Locator,
with Server-owned capability/freshness state and no Ecommerce claim. Existing
Restaurant QR and Quick-service ordering remain available on their prior
Server-priced, idempotent contracts. Takeaway transactions remain closed by
the WP62 Server gate.

## Evidence

- Focused Backend and routing tests: 11/11 passed.
- Public Desktop/Tablet browser tests: 6/6 passed.
- Storefront tenant-routing browser regression: passed.
- Frontend TypeScript and production build: passed.
- Backend/Frontend local Docker images: passed.
- Built Backend image: 48 route groups loaded.
- Full Platform browser regression: 20/20 passed.
- Platform Auditor mutation controls are hidden and the Server still rejects
  both Operations mutations with HTTP 403.
- Tenant Auditor reads the Company audit timeline with HTTP 200 and cannot
  create users (HTTP 403).
- Retail Cashier receives a Server-signed `retail_pos` / `RTL-01` context.
- Signed Tenant A/B isolation returns 404 cross-Tenant and ignores spoofed
  `X-Company-ID` headers.
- Diff whitespace gate: passed.

## UAT and rollback

- Candidate commit: `f753bd3`.
- Backend image: `restaurant-pos-backend:batchc-f753bd3`
  (`sha256:5892d8c1d94ae6c377cba164e84d76788ff311204789b4f0f96506d2f79cb9f0`).
- Frontend image: `restaurant-pos-frontend:batchc-f753bd3`
  (`sha256:190879a0265a82007ee7391c0b90cbb83fda15f84d70b5c301f0b1a34d9d015e`).
- Five-database, Redis and uploads rollback backup passed checksums at
  `/home/behappyaiagent/restaurant-uat-deploy-backups/batch-c-final/restaurant-pos-uat-20260922T164255Z`.
- Public health, Takeaway, Kitchen, Distribution and Storefront routes all
  returned HTTP 200 after deployment and after rollback restoration.
- Restaurant Table QR menu/status remained HTTP 200 with 28 products and an
  open session.
- Kitchen/Distribution/Takeaway writes remained HTTP 409 under their Server
  gates. Production containers were unchanged.
- App-only rollback to `wp64-fafd38a` and restoration to `batchc-f753bd3`
  each reached HTTP 200 in 9 seconds; UAT Postgres, Redis, Nginx and
  Cloudflared container identities did not change.

## Holds

Ecommerce, payment, Digital receipt, customer identity/member portal,
consent, physical/mobile-browser acceptance, Takeaway/Kitchen/Distribution
writes, Production and external-provider/tax actions remain closed.

## Next gate

Batch C's software gate is closed. WP65 may begin on Local/UAT only. Physical
printer/cash/PromptPay/network testing, real Takeaway or Supply-chain writes,
real provider/tax actions, approved Chambo data and Production activation
remain separate explicit gates.
