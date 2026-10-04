# Batch C Phase Gate — Takeaway, Kitchen/Supply Chain and Public Experience

Date: 2026-09-22

Candidate: `f753bd3`

Decision: **SOFTWARE UAT PASS / WP65 MAY BEGIN ON LOCAL AND UAT**

Production decision: **NO-GO / unchanged**

## Accepted scope

- WP62 Takeaway stays a Server-authoritative Dark Launch.
- WP63 Company Kitchen and Distribution stay read-only.
- WP64 Storefront stays Catalog and Branch Locator; Restaurant Table QR and
  Quick-service keep their existing session-scoped order contracts.
- No gate in this document authorizes real Takeaway, Kitchen, Distribution,
  payment, refund, tax, Chambo or Production transactions.

## Local engineering evidence

- Backend access/release/security regression: 42/42 passed.
- Platform browser regression: 20/20 passed.
- Public Desktop/Tablet browser regression: 6/6 passed in the WP64 gate.
- Frontend TypeScript and production PWA build: passed.
- The PWA build now separates vendor bundles so every precache artifact stays
  below the configured 3 MiB limit; the non-blocking 500 KiB chunk warning
  remains.
- Backend and Frontend Docker images built; Backend loaded 48 route groups.

## Seven security/auth closure checks

1. Platform Owner current login/navigation regression passed.
2. Platform routes render only the Platform QA banner, never the persisted
   Tenant persona banner.
3. Tenant Auditor reads Company Audit (HTTP 200) and user creation is denied
   (HTTP 403).
4. Platform Auditor reads Dashboard/Operations (HTTP 200); Usage and Runtime
   snapshot mutations are absent in the UI and denied by the Server
   (HTTP 403).
5. Retail Cashier is issued a signed `retail_pos`, `RTL-01`, Retail database
   context with canonical Cashier permissions.
6. A persistent synthetic Tenant B produces Server-signed sessions; A→B and
   B→A user reads return HTTP 404.
7. Spoofed `X-Company-ID` cannot override either signed Tenant context, and
   the existing business-slug wrong-Tenant browser regression passes.

No QA token, password, access key or other credential is stored in this
evidence.

## UAT deployment

- Source archive SHA-256:
  `0c6b323e240bd6f56b2f7a3cfcb69b686ff51a3d4fe50aa79e8cd63c63d450bc`.
- Backend image:
  `restaurant-pos-backend:batchc-f753bd3`,
  `sha256:5892d8c1d94ae6c377cba164e84d76788ff311204789b4f0f96506d2f79cb9f0`,
  `amd64`.
- Frontend image:
  `restaurant-pos-frontend:batchc-f753bd3`,
  `sha256:190879a0265a82007ee7391c0b90cbb83fda15f84d70b5c301f0b1a34d9d015e`,
  `amd64`.
- Only UAT Backend/Frontend were replaced. UAT Nginx, Cloudflared, Postgres
  and Redis were retained. Production container IDs/images remained exactly
  unchanged.

## UAT functional and gate evidence

- `/`, `/health`, `/health/ready`, `/takeaway`, `/company-kitchen`,
  `/company-distribution` and `/test-company`: HTTP 200.
- Public Storefront: `catalog_locator`; checkout capability `false`.
- Kitchen: `read_only`, writes `false`, attempted write HTTP 409
  `company_kitchen_write_hold`.
- Distribution: `read_only`, writes `false`, attempted write HTTP 409
  `company_distribution_write_hold`.
- Takeaway: `dark_launch`, writes `false`, two existing synthetic shifts read,
  attempted open-shift HTTP 409 `takeaway_write_hold`.
- Restaurant: 24 tables read, active session QR found, public menu HTTP 200
  with 28 products, status HTTP 200 and `session_status=open`.
- Final Backend/Frontend/Nginx/Cloudflared fatal and HTTP 5xx counts: zero.

## Backup and rollback

Rollback backup:
`/home/behappyaiagent/restaurant-uat-deploy-backups/batch-c-final/restaurant-pos-uat-20260922T164255Z`

- Legacy, Platform, Restaurant, Retail and Takeaway dumps, Redis, uploads and
  manifest passed SHA-256 verification.
- `pg_restore` catalogs were readable: 1782 / 342 / 1227 / 442 / 174 items.
- App-only rollback to `restaurant-pos-backend:wp64-fafd38a` reached HTTP 200
  in 9 seconds.
- Restoration to `restaurant-pos-backend:batchc-f753bd3` reached HTTP 200 in
  9 seconds.
- UAT Postgres, Redis, Nginx and Cloudflared container identities did not
  change during the rehearsal.

## Remaining HOLDs

- Physical printer, cash drawer, PromptPay, tablet touch/camera and network
  interruption acceptance.
- Real payment/refund/tax provider and real fiscal documents.
- Approved Chambo real-data dry run/cutover.
- Takeaway, Kitchen and Distribution transaction flags.
- Production deployment and Production flags.

WP65 may now start on Local/UAT for integration, reporting, reconciliation
and release governance without changing any HOLD above.
