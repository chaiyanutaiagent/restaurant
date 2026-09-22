# WP65 UAT Evidence — Integration, Reporting and Governance

Date: 2026-09-23

Environment: UAT only (`restaurant-pos-uat-drill`)

Final candidate: `b3476e3c7b5e56bedb6463f1f61b5f889a309d34`

Decision: **SOFTWARE UAT PASS / PRODUCTION HOLD**

## Immutable release

| Evidence | Value |
|---|---|
| Source archive SHA-256 | `6fb91369c4caed8dc1229546b3348effab57aa7569c4c5325599182768713ec1` |
| Backend image | `restaurant-pos-backend:wp65-b3476e3` |
| Backend image ID | `sha256:56383388dc60bd252f861d7429272a350a878037fa8a287136d08ad7bedd939a` |
| Frontend image | `restaurant-pos-frontend:wp65-7840eba` |
| Frontend image ID | `sha256:b4077f237437fd79dfea833f230f273cbb7f03ff7e12f23bdb993eca5797d788` |
| Runtime version | `wp65-b3476e3` |

The Frontend content did not change in the security correction, so the exact
previously built WP65 Frontend image was retained. Only the UAT Backend was
rebuilt and recreated for the final candidate.

## Backup and migration evidence

The pre-WP65 backup is stored at:

`/home/behappyaiagent/restaurant-uat-deploy-backups/wp65-before/restaurant-pos-prod-20260922T181518Z`

Legacy, Platform, Restaurant, Retail, Takeaway, uploads and Redis artifacts
passed manifest checksum and readability checks. The five `pg_restore` catalog
counts were 1797 / 357 / 1242 / 457 / 189.

Final UAT migration heads:

- Legacy/Shared ERP: `wp65govern0026`
- Platform Core: `p15platform0019`
- Restaurant: `p6restaurant0007`
- Retail: `p13retail0007`
- Takeaway: `p6takeaway0008`

## Authenticated UAT smoke

The bounded UAT QA access path issued signed, 30-minute sessions. No access key,
password, token, webhook secret or API key is stored in this document.

- Nine personas were available. Company Admin and Cashier/Service were
  exercised against the signed Restaurant Company/Branch context.
- Company context, access, overview, Action Center, ERP readiness, governance,
  operational status, devices and integration endpoints returned HTTP 200.
- The governance coverage matrix returned 10 non-Hotel product areas and nine
  governance areas.
- Production and physical-device gates remained `hold`.
- Cashier integration access was denied with HTTP 403.
- A spoofed `X-Company-ID` could not replace the signed tenant.
- A second QA session was revoked and its token then returned HTTP 401.

## Integration security and Server authority

- Header API key: HTTP 200; query-string API key: HTTP 401.
- Wildcard scope creation: HTTP 422.
- Rotated old key and revoked new key: HTTP 401.
- Duplicate incoming webhook source: HTTP 409.
- Valid signature with invalid schema: HTTP 422.
- Invalid or expired webhook signature: HTTP 401.
- Webhook secrets/ciphertext were absent from API responses.
- A synthetic order with incorrect client price and total entered
  `needs_review`; the Server price was retained and the record was rejected
  through the review path without fulfillment/provider side effects.

The first WP65 candidate exposed one rejected synthetic API key in the Uvicorn
access URL. That key had already been revoked. Candidate `b3476e3` adds access
log query-secret redaction. The final fresh-container scan found zero
`api_key=erppos_` occurrences and one expected
`api_key=[REDACTED]` occurrence.

## Public route and visual-shell evidence

The final candidate returned HTTP 200 for `/`, `/health`, `/health/ready`,
`/company/governance`, `/integrations`, `/pos`, `/takeaway`,
`/company-kitchen`, `/company-distribution` and `/test-company`.

The live browser inspection verified the Foodchainservice login/QA-access shell
and correct Company identifier. Authenticated Company/Governance behavior was
verified through the signed API smoke above; no UAT secret was entered into the
browser automation. Local browser regression remains 46/46 across Platform,
Company, Kitchen, Distribution, Takeaway, Public, Integration and Retail.

## Rollback and restoration

- App-only rollback to Backend/Frontend `batchc-f753bd3` reached Backend health
  and Frontend HTTP 200 in approximately 11 seconds.
- Restoration to Backend `wp65-b3476e3` and Frontend `wp65-7840eba` reached the
  same checks in approximately 14 seconds.
- Post-restore authenticated smoke, migration heads, public routes and access
  log redaction all passed again.
- UAT Postgres, Redis, Nginx and Cloudflared container identities did not change.
- Production Backend, Frontend, Postgres, Redis, Nginx and Cloudflared container
  identities and images remained unchanged.

## Retained evidence and HOLDs

Synthetic revoked API-key rows and rejected external-order audit evidence are
retained until Product Owner sign-off. The guarded QA cleanup helper was not
executed.

The following remain outside this pass:

- physical printer, cash drawer, PromptPay, tablet camera/touch and real
  network-interruption acceptance;
- live provider/refund/tax transactions and real fiscal documents;
- Takeaway, Central Kitchen and Distribution transaction activation;
- Retail Production source cutover and Chambo real-data cutover;
- mutable incident response and retention/legal-hold workflows;
- every Production deployment or Production flag.
