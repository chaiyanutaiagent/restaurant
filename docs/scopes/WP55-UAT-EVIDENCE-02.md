# WP55 UAT Evidence — Retail Foundation and Scan-first Sale

Date: 2026-09-22
Environment: UAT only
Production: unchanged and not authorized

## Immutable candidate

| Item | Identity |
|---|---|
| Source commit | `2922af0` |
| Backend image | `restaurant-pos-backend:wp55-2922af0` |
| Backend image ID | `sha256:233a16090dad27c09a078364f25f545008f10517c9f4932a7f70da93c49489a6` |
| Frontend image | `restaurant-pos-frontend:wp55-2922af0` |
| Frontend image ID | `sha256:70d5df9d5d88fa36c3a98dc56582d3391843829a1007420478211e981a33bebc` |
| Public route | `https://uat-pos.foodchainservice.com/` |

## Passed evidence

- `/health` and `/health/ready` passed after deployment.
- Public Table QR exposed exactly 28 addable Restaurant products, six unique product categories plus `ทั้งหมด`, and no Retail product leakage.
- Staff Takeaway displayed the same signed 28-item Restaurant menu.
- A fresh Device Status dialog contained an accessible description and produced no missing-description console warning.
- Frozen frontend type-check/build passed and the served asset matched the frozen build.
- Focused WP55/WP56 checks passed 16/16 after the next-package changes and UAT credential guard hardening were applied.
- Full backend regression passed 486/486 after fixing the Docker fallback runner to include `/scripts`.

## Authenticated Retail checkpoint — passed with WP56 candidate

The bounded `uat.retail-cashier` identity was provisioned through the guarded UAT-only command. Engineering did not weaken the Server guard and did not store credentials or tokens in source or evidence. The authenticated checkpoint passed against the WP56 candidate:

1. `/pos` opened with Server-signed `retail_pos` Company/Brand/Branch context.
2. Retail-only navigation was visible and Restaurant Table/QR/Takeaway/KDS controls were absent.
3. The assigned Retail SKU resolved from the signed Catalog and used the Server price.
4. Unknown and unavailable barcodes produced persistent recovery states without losing the cart.
5. Retail Hold and Return/Refund remained explicitly gated for WP57.

The controlled cash-only WP56 sale is recorded separately in `WP56-UAT-EVIDENCE-02.md`. Production source cutover remains unauthorized.

## QA finding and remediation

QA found that the clean Docker fallback regression runner copied backend and frontend sources but omitted `/scripts`, causing one runner-contract error. The runner now copies `/scripts`; the complete pre-hardening suite passes 486/486 and the final focused suite passes 16/16. This remediation is included with WP56 and does not alter runtime behavior.

An UAT administrator credential used during automated verification was rotated through the bounded UAT-only password-rotation command. Refresh tokens were revoked and an audit entry was written. No credential or token is stored in this repository or evidence.

## Production identity checkpoint

Production identities were unchanged during WP55 verification:

- backend `restaurant-pos-backend:auth-a0fdccf` / `sha256:f93cb840b85a2258a18b7542c7e09ce74c3b67221dd25305738c22922ffaab89`
- frontend `restaurant-pos-frontend:ui-e4200ca` / `sha256:240b1ef60b0bc7750328d38b4557d93a614fbed82cda0d49906b18ad67466c2b`
- nginx `restaurant-pos-nginx:unified-d528512` / `sha256:c04273dffea6d10159bd142bc94d16e00b01f5763c76ebaabbfa5a896cce94fb`
- cloudflared `cloudflare/cloudflared:2026.7.0` / `sha256:5e49861633763e8933475477c20bae6039ed47f32c1d267a34babc347f28f0df`
- postgres `postgres:15-alpine` / `sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f`
- redis `redis:7-alpine` / `sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2`

## Evidence conclusion

WP55 implementation, Restaurant regression and the authenticated Retail context matrix pass. After independent QA, the bounded UAT persona was disabled and all refresh sessions/active assignments were revoked. Production remains NO-GO.
