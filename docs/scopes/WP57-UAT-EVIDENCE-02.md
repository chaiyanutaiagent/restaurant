# WP57 UAT Evidence — Retail Hold, Cash Return and Shift Operations

Date: 2026-09-22  
Environment: UAT only  
Production: unchanged and not authorized

## Immutable candidate

| Item | Identity |
|---|---|
| Runtime source commit | `bf36ecf` |
| Runtime source archive SHA-256 | `faeb0cb4c26afa35e772f73ebf974ec80349b7a484b1ac055f7fcb447aaa5b6b` |
| Final authenticated harness commit | `885ce67` |
| Harness source archive SHA-256 | `4fa5a9570fae500d60d74b2cb7b102488d736bf66420b5e85a8d394b577aecaa` |
| Backend image | `restaurant-pos-backend:wp57-bf36ecf` |
| Backend image ID | `sha256:5ed1c4284ef4600656838a95ddce4de3c868c7931d8cf586643e79aa7b35480f` |
| Frontend image | `restaurant-pos-frontend:wp57-bf36ecf` |
| Frontend image ID | `sha256:6b0548d97c1a63aacfce8d2fa017f5f0c2b3c3cf61149b407ed403e0b96e01ce` |
| Public route | `https://uat-pos.foodchainservice.com/` |

## Data protection and schema

- The final pre-deployment backup is stored at `/home/behappyaiagent/restaurant-uat-deploy-backups/wp57-before/restaurant-pos-prod-20260922T071449Z`.
- All five PostgreSQL dump catalogs, the Redis archive, the uploads archive and their checksums passed verification before deployment.
- Final heads are Platform `p13platform0017`, Restaurant `p6restaurant0007`, Retail `p13retail0007` and Takeaway `p6takeaway0008`.
- Retail `p11retail0005` → `p13retail0007` was rehearsed as upgrade → downgrade → upgrade on an isolated database.
- Only the UAT Retail schema advanced. Production migrations, feature flags and data sources were not changed.

## Engineering results

- WP56/WP57 focused tests passed 19/19.
- Full backend regression passed 499 tests with one intentional skip.
- Frontend type-check and production/PWA build passed; 4,243 modules were transformed.
- Static checks, Python compile, migration checks and `git diff --check` passed.

## Authenticated UAT results

The guarded harness ran only when the runtime proved development/UAT, Platform identity authority, Retail operational authority and disabled auth bypass. It generated random temporary credentials in memory and never wrote credentials to source or evidence.

- Signed Retail Company/Brand/Branch context resolved for a separate cashier requester and manager approver.
- Hold creation and idempotent replay returned one Server-priced draft. Cross-staff listing, claim, resume, stale-version rejection and conversion passed.
- Retail offline sale failed closed with `retail_offline_not_authorized`.
- A controlled cash sale used the Server price. Settled-payment Void failed closed and directed the workflow to Return.
- Cash Return quote → different-user approval → execute → idempotent replay → cash confirmation passed.
- Return wrote exactly one linked negative Payment, restored sellable stock exactly once and recorded tax state `not_required` without a Credit Note.
- Exchange, provider inquiry/retry and tax retry remained fail-closed.
- Hold and refund audit tables rejected mutation, preserving append-only evidence.
- Cash movement required approval, replayed idempotently and recorded journal state `not_applicable`; no shared accounting journal write occurred.
- Shift close blocked while Return settlement was pending, then summary/close passed. Handover failed closed without a paired Counter.
- Public `/`, `/pos`, `/admin` and `/health/ready` returned HTTP 200 after final restore. Backend readiness returned `ok` and no traceback, 500 or missing-relation pattern appeared in the final logs.

## Test-persona containment

- After each run, the exact temporary cashier and manager identities were disabled in Platform, Retail and the Legacy source copy.
- Platform active refresh-token count for those identities was zero.
- Active Platform staff assignments, if any, were revoked with a UAT-only reason and the disable action was audited.
- Commit `885ce67` makes the Legacy-copy disable part of the harness `finally` path so a failed or successful future run remains fail-closed.
- The evidence retains operational audit rows but no usable UAT credential.

## Rollback and Production isolation

- App-only rollback from WP57 to backend `wp56-81aba50` and frontend `wp56-f02c9a6` passed without schema downgrade.
- Backend health was `healthy` and readiness returned `ok` on the rollback images.
- Restore to backend/frontend `wp57-bf36ecf` passed; all four public routes returned HTTP 200.
- Production container names, images and container IDs matched the pre-deployment checkpoint exactly for backend, frontend, nginx, cloudflared, PostgreSQL and Redis.

## Boundary retained

WP57 proves the online Retail Cash Pilot software contract only. It does not authorize Exchange, provider refund, live PromptPay/card/transfer, real tax/Credit Note, Loyalty, Retail offline sale, Production data-source cutover or any Takeaway/Central Kitchen write. Scanner, printer, cash drawer and stateful network-loss/recovery remain WP58 physical acceptance.
