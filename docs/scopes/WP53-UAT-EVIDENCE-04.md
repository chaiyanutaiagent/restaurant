# WP53 UAT Evidence — Offline and Sync Recovery UX

Date: 2026-09-22  
Environment: `https://uat-pos.foodchainservice.com`  
Production: **unchanged**

## Accepted build

- Feature commit: `538d269` — Restaurant Offline Sync Center.
- Counter hydration fix: `ca3fb25`.
- Source archive SHA-256: `3df40df3bd1396e7a198a602ece0ba9c25ed5e676ecfd38971de68d93555bf91`.
- UAT frontend image: `restaurant-pos-frontend:wp53-ca3fb25`.
- UAT image ID: `sha256:60e0d7162ca069d2a71fb4eb7fbd1e879309aace9a3d077f44b8f7a81f178ce7`.
- UAT Backend remained `restaurant-pos-backend:wp52-e4e3ad9`.

## Engineering evidence

- Frontend TypeScript check: PASS.
- Frontend production build: PASS; existing chunk-size advisory only.
- WP53 and WP52 static contract suites: 11 tests PASS.
- Source diff check: PASS.
- No Backend or database schema change in WP53.

## Paired-Counter browser evidence

1. Rotated and paired the existing UAT Counter `UI-DEVICE-01` using the normal one-time flow.
2. Device gate restored the existing Staff session for `uat.branch-manager`.
3. `/pos/offline-sync` displayed the expected Company, Branch, Counter, Staff and open-shift context.
4. Real browser outbox empty state reported zero pending/review/reconciled rows; no hard-coded rows appeared.
5. Manual `ตรวจและซิงก์` completed and disclosed inquiry-before-replay behavior.
6. The page passed visual inspection at 1024×768 tablet landscape without horizontal overflow or
   hidden Network/queue status.
7. The paired Counter and Staff context remained available after the rollback/restore rehearsal.

## Route and health evidence

`/`, `/pos`, `/pos/offline-sync`, `/admin`, `/health` and `/health/ready` returned HTTP 200 after deploy.
The final UAT nginx five-minute/ten-minute inspection found zero HTTP 5xx responses.

## Rollback evidence

- UAT frontend rollback: `wp53-ca3fb25` → `wp52-0d0e021`, completed in less than one second at
  shell timer resolution; health remained 200.
- UAT frontend restore: `wp52-0d0e021` → `wp53-ca3fb25`, completed in less than one second at
  shell timer resolution; health remained 200.
- Only the UAT frontend container was recreated.

Production container image/short IDs remained:

- Backend: `restaurant-pos-backend:auth-a0fdccf` / `f6e08435721a`
- Frontend: `restaurant-pos-frontend:ui-e4200ca` / `857e0dbab1a2`
- Nginx: `restaurant-pos-nginx:unified-d528512` / `aea97e7f90f7`
- Cloudflared: `cloudflare/cloudflared:2026.7.0` / `ae6862f8a09f`
- Postgres: `postgres:15-alpine` / `3565e3fd72ad`
- Redis: `redis:7-alpine` / `76658d7ad2fd`

## Evidence boundary

The browser-control safety boundary prevented direct fixture insertion into IndexedDB. No synthetic
row was written and no Server transaction was created. Therefore this evidence does **not** claim that
pending, lost-acknowledgement, needs-review or replay behavior passed end-to-end in the browser.
Airplane mode, real reconnect, app restart, printer/cash-drawer failure, real PromptPay/provider and
multi-device concurrency remain the stateful/physical WP54 UAT gate.

