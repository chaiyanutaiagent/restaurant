# WP51 UAT Evidence — Hold Draft and Order Center

Date: 2026-09-21
Environment: UAT only
Decision: **PASS**

## Release identity

| Item | Evidence |
|---|---|
| Feature commit | `b1a2701` (`feat: deliver WP51 hold and order center UX`) |
| Smoke-harness commit | `3a398bd` (`test: align hold smoke with shift blocker envelope`) |
| Immutable application release | `/home/behappyaiagent/restaurant-uat-releases/b1a2701` |
| Immutable harness release | `/home/behappyaiagent/restaurant-uat-releases/3a398bd` |
| Application archive SHA256 | `8b2ff756520112a74df24dfb623ec5ac63fb947848d2708ba02f38c5437abdd5` |
| Harness archive SHA256 | `f6e0591e739ea2f8ce56be3c087993ab7438ea37d444d5d7890c000a4852452f` |
| Backend image | `restaurant-pos-backend:wp51-b1a2701` |
| Backend image ID | `sha256:7e30fe8411a576a6100e22a03e3048e88aa1d68303a0684c4b3244f9396458d5` |
| Frontend image | `restaurant-pos-frontend:wp51-b1a2701` |
| Frontend image ID | `sha256:4a662a496ae7da0a720372b71e950fc7da377402a092d3a1fc6bcaef1a25cab4` |
| UAT stack | `restaurant-pos-uat-drill` |
| Pre-deploy backup | `/home/behappyaiagent/restaurant-uat-deploy-backups/wp51-before/restaurant-pos-prod-20260921T125006Z` |

The backup covers Platform, Restaurant, Retail, Takeaway and legacy PostgreSQL databases plus Redis
and uploads. No Production service or data source was used for this UAT.

## Runtime boundary

| Setting | Final UAT value |
|---|---|
| Identity | `platform_core` |
| Restaurant service | `legacy` |
| Retail service | `retail` — unchanged; no source switch |
| Takeaway service | `takeaway` — pre-existing; no WP51 transaction authorization |
| Reference projectors | Platform and Retail enabled |
| Company Kitchen writes | `false` |
| Company Distribution writes | `false` |
| UAT authentication bypass | `false` |

WP51 did not enable Production flags, Takeaway/Central Kitchen writes, Retail cutover, a live payment
provider or real tax documents.

## Engineering and API evidence

- Full backend regression: PASS — 455 tests, 1 skipped.
- Focused WP51 tests: PASS — 2 tests.
- Existing WP44 regression: PASS — 4 tests.
- Frontend TypeScript check and production/PWA build: PASS.
- UAT `WP44 Hold Draft API smoke`: PASS against the deployed WP51 backend.
- Create/replay, Server price authority and no Sale/Payment/Stock side effect while held: PASS.
- One-winner claim, stale-version conflict, claim/release, resume/idempotency and conversion: PASS.
- Discard with reason, expiry/reopen, price-change review, append-only audit, reassign and
  tenant/Branch isolation: PASS.
- Shift close/handoff blocker uses the canonical WP50 `shift_close_blocked` envelope: PASS.

The first smoke invocation correctly reached the new WP50 blocker envelope but the old harness expected
the nested blocker as a top-level code. The harness was corrected in `3a398bd` and the complete rerun
passed. Its isolated draft and shift in `APPROVAL-3971e92d` were then discarded/closed through the normal
API with audit reason `WP51 failed smoke cleanup`. The passing run `APPROVAL-61444fc2` also ended closed.

## Formal browser UAT

Normal authentication with `uat.branch-manager` was used; no bypass was enabled and no password was
written to Git or evidence.

| Check | Result |
|---|---|
| POS Hold workspace | PASS — separate list/detail regions, search, sort, active/mine/Counter/history filters and explicit empty state |
| Hold source-of-truth label | PASS — clearly states Server/all-Counter ownership and no KDS/stock/tax/payment side effects |
| Order Center | PASS — canonical state/source filters, 100 Server-backed UAT orders, list/detail view and real “open order/add items” action |
| Search | PASS — exact order-number search reduced the list to one matching order while preserving its detail |
| Desktop 1440×900 | PASS — document width equals viewport, no page-level horizontal overflow, no visible control below 44×44px |
| iPad landscape 1024×768 | PASS — Hold list/detail and Order Center detail remain available, no page-level horizontal overflow, no visible control below 44×44px |
| Accessibility/runtime | PASS — Hold dialog has a valid label and description relationship; clean WP51 page load recorded no console warning/error |

Automated/API evidence covers mutation, conflict, revalidation, permission and fail-closed behavior.
Physical network loss, printer, cash drawer and PromptPay remain WP54 physical UAT and are not claimed.

## Rollback rehearsal and recovery

WP51 adds no migration, so application-image rollback retained the current database and data volumes.

An initial operator command incorrectly overrode the release-pinned `PRODUCTION_ENV_FILE` with a relative
`.env`. The WP50 backend therefore rejected its incomplete configuration before accepting traffic and UAT
returned 502. No database, Production service or external route changed. WP51 was reapplied from its
immutable release and returned healthy in 9 seconds. The runbook now forbids that override and requires
resolved Compose preflight.

| Operation | Result |
|---|---|
| Corrected rollback to `restaurant-pos-backend:wp50-7af7a99` + `restaurant-pos-frontend:wp50-63e8496` | PASS — 11 seconds; public health/readiness OK |
| Restore WP51 backend/frontend images | PASS — 11 seconds; public health/readiness OK |
| Final backend | `restaurant-pos-backend:wp51-b1a2701`, healthy |
| Final frontend | `restaurant-pos-frontend:wp51-b1a2701`, running |
| PostgreSQL/Redis/nginx/cloudflared | Unchanged during corrected app-only rehearsal |

## Production isolation

Production retained its pre-WP51 identities:

| Service | Image | Container ID |
|---|---|---|
| Backend | `restaurant-pos-backend:auth-a0fdccf` | `f6e08435721a` |
| Frontend | `restaurant-pos-frontend:ui-e4200ca` | `857e0dbab1a2` |
| Nginx | `restaurant-pos-nginx:unified-d528512` | `aea97e7f90f7` |
| Cloudflared | `cloudflare/cloudflared:2026.7.0` | `ae6862f8a09f` |
| PostgreSQL | `postgres:15-alpine` | `3565e3fd72ad` |
| Redis | `redis:7-alpine` | `76658d7ad2fd` |

Production deployment and activation remain **NO-GO**.
