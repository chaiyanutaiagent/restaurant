# WP52 — UAT Plan: Restaurant Exceptions and Receipt Center

Date: 2026-09-21
Environment: Local, UAT and Sandbox only
Production: Not authorized

## Candidate

- Frontend feature commit: `44a1b36`
- Offline-boundary correction: `d12b327`
- Final smoke-harness commit: `e4e3ad9`
- UAT stack: `restaurant-pos-uat-drill`
- Existing Restaurant database and WP43/WP45/WP46 contracts remain authoritative.

## Gate sequence

1. Pass TypeScript, production/PWA build, focused WP tests and full backend regression.
2. Build immutable UAT images with the Refund simulator enabled only in the UAT frontend.
3. Re-run the WP43 pricing, WP45 cancellation and WP46 refund/tax API smokes.
4. Verify normal authentication, POS loading and responsive exception surfaces at 1440×900 and 1024×768.
5. With a paired UAT Counter and open Staff shift, cover Bill Center search/detail, Void eligibility, cancellation preview, Manager approval and Refund recovery states.
6. Rehearse application-only rollback to WP51 and restore WP52.
7. Verify public health/routes, no recent nginx 5xx and unchanged Production identities.

## Fail-closed rules

- Direct online WAP/Store endpoints must reject `is_offline=true`; authorized offline work must use the WP47 sync envelope.
- No action may fabricate approval, provider completion, tax submission or exchange success.
- Unpaired Counter, offline approval, provider unknown and missing contract states remain blocked.
- No real tax/Credit Note, live provider, Retail cutover, Takeaway/Central Kitchen activation or Production deployment.

## Rollback

- Restore WP51 backend/frontend from `/home/behappyaiagent/restaurant-uat-releases/b1a2701`.
- Keep PostgreSQL, Redis, nginx and Cloudflare Tunnel unchanged.
- Restore final WP52 from `/home/behappyaiagent/restaurant-uat-releases/0d0e021` after health verification.
