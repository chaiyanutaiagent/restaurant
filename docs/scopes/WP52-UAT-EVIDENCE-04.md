# WP52 UAT Evidence — Restaurant Exceptions and Receipt Center

Date: 2026-09-21
Environment: UAT only
Decision: **PARTIAL PASS — engineering, API and rollback passed; paired-Counter visual actions pending**

## Release identity

| Item | Evidence |
|---|---|
| Frontend feature commit | `44a1b36` (`feat: compose WP52 restaurant exception UX`) |
| Offline-boundary correction | `d12b327` (`fix: require authorized offline order sync`) |
| Final harness commit | `e4e3ad9` (`test: align refund smoke with shift blockers`) |
| Final immutable release | `/home/behappyaiagent/restaurant-uat-releases/e4e3ad9` |
| Final archive SHA256 | `ee495f1d36bc579d6b8c3df4f9ef451fa71c3aa5f89223f5bc880d56021b5a89` |
| Frontend archive SHA256 | `83c2b2f8a6e0165168830027376540112abf3c3f494e89e2b8fdac2a8ad79fca` |
| Backend image | `restaurant-pos-backend:wp52-e4e3ad9` |
| Backend image ID | `sha256:309d824b50079a5ff2f8d4c14d27910c6768d688bfb0211a5b50ce954e9ee885` |
| Frontend image | `restaurant-pos-frontend:wp52-44a1b36` |
| Frontend image ID | `sha256:9dc03081e4933458444d2f55caece4693263c5c30b2e62760ab453a1159affb8` |
| UAT stack | `restaurant-pos-uat-drill` |

## Local engineering evidence

- Frontend TypeScript check: PASS.
- Frontend production/PWA build: PASS; existing large-chunk warning only.
- Focused WP regression: PASS — 60 tests.
- Full backend regression: PASS — 460 tests, 1 skipped.
- Git whitespace validation: PASS.

## UAT defect detection and correction

The first WP43 smoke run found that the legacy online WAP endpoint accepted `is_offline=true` after the
WP47 authorized sync path was introduced. Server pricing still remained authoritative, but the request
could bypass the signed Offline Sync envelope. Commit `d12b327` now rejects this flag on both direct WAP
and Brand Store online endpoints with the existing machine-readable `stale_price` response. The signed
`/orders/sync` routes remain unchanged. The full WP43 smoke then passed.

The first WP46 rerun reached the correct WP51 `shift_close_blocked` envelope containing the
`refunds_pending` blocker, while its older harness expected the blocker at the top level. Commit
`e4e3ad9` aligned the assertion without changing Refund behavior. The rerun passed.

## API and authority evidence

| Contract | Result |
|---|---|
| WP43 price/discount/override | PASS — authority, tamper resistance, approval, replay, version and offline fail-closed checks |
| WP45 cancellation/Waste/Audit | PASS — stage, maker-checker, KDS acknowledgment, Waste and immutable audit checks |
| WP46 provider refund/tax | PASS — quote, remaining balance, cash/provider recovery, concurrency, sandbox webhook and synthetic non-fiscal tax checks |

No live provider call or real tax/Credit Note submission occurred.

## Formal browser UAT completed

Normal `uat.branch-manager` authentication was reused; authentication bypass stayed disabled and no
credential was written to Git or evidence.

| Check | Result |
|---|---|
| Current WP52 asset | PASS — POS showed `ศูนย์บิล`, current signed menu and Server status |
| Discount workspace | PASS — amount/percent modes, quick percentages, before/discount/after totals, missing structured-reason disclosure and Server-authority copy |
| Desktop 1440×900 | PASS for POS/Discount composition |
| iPad landscape 1024×768 | PASS for POS/Discount composition; dialog remained readable and touch-sized |
| Unpaired Counter state | PASS — Staff shift open stayed disabled with explicit pairing requirement |

The current browser is not paired to a UAT Counter. Creating or rotating a pairing credential is a
persistent-access action and was not performed implicitly. Therefore Bill Center search/detail, safe
Void, cancellation preview/approval and Refund recovery were not claimed as formal browser passes in
this run. Their Server contracts passed API smoke and their frontend composition passed build/tests.

## Runtime boundaries

| Setting | Final UAT value |
|---|---|
| Authentication bypass | `false` |
| Refund provider | `sandbox` |
| Synthetic UAT Credit Note | `true` — non-fiscal/not submitted only |
| Offline mode | `true` — pre-existing WP47 UAT allowlisted path |
| Company Kitchen writes | `false` |
| Company Distribution writes | `false` |

## Public health and rollback

- `/`, `/pos`, `/admin`, `/health` and `/health/ready`: HTTP 200.
- UAT nginx HTTP 5xx during the final 15-minute check: 0.
- WP52 → WP51 backend/frontend rollback: PASS — 13 seconds; local proxy health passed.
- WP51 → WP52 restore: PASS — 12 seconds; local and public health passed.
- PostgreSQL, Redis, nginx and Cloudflare Tunnel were not recreated during the corrected rehearsal.

## Production isolation

| Service | Image | Container ID |
|---|---|---|
| Backend | `restaurant-pos-backend:auth-a0fdccf` | `f6e08435721a` |
| Frontend | `restaurant-pos-frontend:ui-e4200ca` | `857e0dbab1a2` |
| Nginx | `restaurant-pos-nginx:unified-d528512` | `aea97e7f90f7` |
| Cloudflared | `cloudflare/cloudflared:2026.7.0` | `ae6862f8a09f` |
| PostgreSQL | `postgres:15-alpine` | `3565e3fd72ad` |
| Redis | `redis:7-alpine` | `76658d7ad2fd` |

Production remained unchanged and is **NO-GO**.

