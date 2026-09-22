# WP56 UAT Evidence — Retail Exceptions, Cash Pilot and Receipt

Date: 2026-09-22  
Environment: UAT only  
Production: unchanged and not authorized

## Immutable candidate

| Item | Identity |
|---|---|
| Source commit | `81aba50` |
| Source archive | `restaurant-wp56-81aba50.tar.gz` |
| Archive SHA-256 | `1595ed300cab2c28a90bf5c3afd124c294d77abc457023d5dc85013c5f83abc3` |
| Backend image | `restaurant-pos-backend:wp56-81aba50` |
| Backend image ID | `sha256:437379f20f1b0045ae0f5e812bc44afd56fc809753450f514bbcbf010ba61ee3` |
| Frontend image | `restaurant-pos-frontend:wp56-81aba50` |
| Frontend image ID | `sha256:1d82a11f44328eb1e3682d14c70a51e2a767e35bca70a6d59a900856254f0d31` |
| Public route | `https://uat-pos.foodchainservice.com/` |

## Data protection and schema

- The verified final pre-deployment backup is stored at `/home/behappyaiagent/restaurant-uat-deploy-backups/wp56-final-before/restaurant-pos-prod-20260922T044247Z`.
- All five PostgreSQL dump catalogs, uploads archive and Redis archive passed integrity/catalog checks before cutover.
- Final heads: Platform `p13platform0017`, Restaurant `p6restaurant0007`, Retail `p11retail0005`, Takeaway `p6takeaway0008`.
- `p10retail0004` → `p11retail0005` was rehearsed upgrade → downgrade → upgrade on an isolated database. No Hold Draft table was introduced into Retail.

## Engineering and authenticated UAT results

- Frontend type-check and production/PWA build passed; 4,243 modules transformed. The existing large-bundle advisory remains non-blocking.
- Final focused WP55/WP56 tests passed 21/21; full backend regression passed 493/493.
- Signed `retail_pos` Company/Brand/Branch context opened with 16 assigned Retail products and no Restaurant-only navigation.
- Valid SKU `UI-RTL-001` used the Server-authoritative price ฿37. Unknown barcode `9999999999999` and unavailable barcode `8850000000001` produced persistent recovery states and retained the cart.
- PromptPay, card, transfer, split payment, offline sale, Hold and Return/Refund remained fail-closed. Retail refund mutations return `retail_return_not_ready` until WP57.
- Controlled cash-only sale `SO20260922-0001` completed at ฿37; Payment was settled cash, stock changed 12 → 11, the pricing quote was consumed and the sale-completed outbox event was pending for projection.
- Bill Center showed the controlled sale and receipt after explicit refresh. The Return/Refund button was disabled with the WP57 reason.
- Public `/health/ready` returned `ok`; no post-deploy 500, schema exception or traceback was found.

## Deployment incident and recovery

The first backend recreate referenced `.env` instead of the existing separated UAT runtime file, so required runtime configuration was absent and the container restarted. No migration or data write occurred during that failed start. The release was corrected by copying the existing runtime file without exposing its contents and recreating only the UAT backend. Health recovered before acceptance testing. Production was untouched.

## Rollback and restore rehearsal

- App-only rollback to backend/frontend `d6200fc` passed in 11 seconds without schema downgrade.
- Restore to backend/frontend `81aba50` passed in 10 seconds.
- Public readiness passed after both transitions, and the signed Retail UI passed again after final restore.

## Production identity checkpoint

Production remained unchanged:

- backend `restaurant-pos-backend:auth-a0fdccf` / `sha256:f93cb840b85a2258a18b7542c7e09ce74c3b67221dd25305738c22922ffaab89`
- frontend `restaurant-pos-frontend:ui-e4200ca` / `sha256:240b1ef60b0bc7750328d38b4557d93a614fbed82cda0d49906b18ad67466c2b`
- nginx `restaurant-pos-nginx:unified-d528512` / `sha256:c04273dffea6d10159bd142bc94d16e00b01f5763c76ebaabbfa5a896cce94fb`
- cloudflared `cloudflare/cloudflared:2026.7.0` / `sha256:5e49861633763e8933475477c20bae6039ed47f32c1d267a34babc347f28f0df`
- postgres `postgres:15-alpine` / `sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f`
- redis `redis:7-alpine` / `sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2`

## Gate conclusion

WP56 software UAT and rollback/restore pass. The phase remains **conditional / Production NO-GO** until the independent QA retest finishes, the bounded UAT persona is disabled with sessions revoked, and physical tablet/scanner/printer/cash-drawer/network-loss evidence is attached. No live provider transaction, real tax document or Retail Production data-source cutover is authorized.
