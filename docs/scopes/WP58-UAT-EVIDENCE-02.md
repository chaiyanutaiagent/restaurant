# WP58 UAT Evidence — Retail Recovery and Counter Readiness

Date: 2026-09-22
Environment: UAT only
Production: unchanged and not authorized

## Immutable candidate

| Item | Identity |
|---|---|
| Source commit | `527ba6d` |
| Source archive SHA-256 | `e64fc18ec699df5a88633216b542b1443e844c4b99bd2f6804099c97080ac659` |
| Backend image | `restaurant-pos-backend:wp58-527ba6d` |
| Backend image ID | `sha256:43b20e5f0449aa98f808877b85d54f08a958840eab4bb0142d4965813abb5b53` |
| Frontend image | `restaurant-pos-frontend:wp58-527ba6d` |
| Frontend image ID | `sha256:eb726d2f6e41c4640126596939acbf50cf504946e1f265e9858aa244eb980ed6` |
| Public route | `https://uat-pos.foodchainservice.com/` |

## Data protection and boundaries

- Final pre-deployment backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/wp58-before/restaurant-pos-prod-20260922T092148Z`.
- Legacy, Platform, Restaurant, Retail and Takeaway dumps, Redis and uploads were non-empty and received SHA-256 checksums before deployment.
- No schema migration was required. Final heads remained Platform `p13platform0017`, Restaurant `p6restaurant0007`, Retail `p13retail0007` and Takeaway `p6takeaway0008`.
- UAT remained Platform identity + Retail operational data. Production Retail remained on its existing Legacy source.

## Engineering and software UAT results

- Frontend TypeScript gate and production/PWA build passed; 4,244 modules were transformed.
- WP54/WP58 focused checks passed 11/11 locally.
- WP55–WP58 immutable-image regression passed 32/32.
- Full immutable-image backend regression passed 504/504. The default-contract runner used `.env.example`; a separate run under live UAT boundary settings correctly demonstrated that four default-value assertions are environment-specific rather than product failures.
- Authenticated Retail Hold/Return/Shift journey passed on the WP58 runtime, including Server pricing, offline fail-closed behavior, maker-checker cash Return, exact-once effects, shift controls and disabled provider/tax/Exchange actions.
- Temporary cashier/manager users were disabled in Platform, Retail and Legacy. Active Platform refresh tokens and active staff assignments for the run were zero.

## WP58 recovery and readiness contract

- Retail offline payment remains blocked with `retail_offline_not_authorized`.
- Local pending-sale records are selected by exact Company/Branch/User/business context. The browser online event has no authority to send a financial queue without signed context.
- Legacy local rows without context are quarantined as `needs_review` and are never auto-sent.
- Server sync responses expose `client_order_id` for per-item acknowledgement. Missing acknowledgement becomes a review state while preserving the original client ID.
- Retail Counter Readiness adds automatic policy/data-boundary checks and separate physical checks for scanner, receipt printer, cash drawer, cash journey, network/lost-ack and reconciliation.
- Browser access reached the correct guarded redirect `/login?next=/pos/offline-sync`; the login page rendered with no browser-console error. No password/token was transmitted during this visual check, so authenticated visual inspection remains a recorded limitation rather than an inferred pass.

## Rollback, restore and Production isolation

- App-only rollback to backend/frontend `wp57-bf36ecf` passed in 11 seconds; `/`, `/pos`, `/admin` and `/health/ready` returned HTTP 200.
- Restore to `wp58-527ba6d` passed in 12 seconds; all four routes returned HTTP 200 and the backend returned healthy.
- The rollback did not downgrade schema or restore data.
- Final logs contained no traceback, HTTP 500, missing-relation or undefined-table pattern.
- Production backend, frontend, nginx, cloudflared, PostgreSQL and Redis image/container identities matched the pre-deployment checkpoint exactly.

## Physical evidence still open

No real scanner, receipt printer, cash drawer, payment terminal, tablet Counter or controlled network-loss test was executed. These checks remain `UNVERIFIED / HOLD`. Browser/API/software evidence is not physical acceptance.
