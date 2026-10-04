# WP50 UAT Evidence — Restaurant Shift Operations

Date: 2026-09-21
Environment: UAT only
Decision: **PASS**

## Deployment identity

| Item | Evidence |
|---|---|
| Feature commit | `7af7a99` (`feat: implement WP50 restaurant shift operations`) |
| Formal-role harness | `9f3cff0` (`test: align WP50 UAT role permissions`) |
| Final UAT candidate | `63e8496` (`fix: meet POS dialog touch target baseline`) |
| Runtime backend release | `/home/behappyaiagent/restaurant-uat-releases/7af7a99` |
| Final candidate release | `/home/behappyaiagent/restaurant-uat-releases/63e8496` |
| Backend image | `restaurant-pos-backend:wp50-7af7a99` |
| Backend image ID | `sha256:2c37ef090181e29dfdbd886fc4cdfa182d5eaa2d0c1659748778a67dc8b22af3` |
| Frontend image | `restaurant-pos-frontend:wp50-63e8496` |
| Frontend image ID | `sha256:f4049bec8c3db3804ad01828b9a1aba488faef51a02578d859f898f02455f529` |
| UAT stack | `restaurant-pos-uat-drill` |
| UAT backup | `/home/behappyaiagent/restaurant-uat-deploy-backups/wp50-before/restaurant-pos-prod-20260921T043545Z` |
| Main migration | `wp50shift0024 (head)` |
| Retail compatibility migration | `p9retail0003 (head)`; additive only |

The pre-deploy backup contains five verified PostgreSQL restore catalogues plus Redis and upload archives. The Retail migration supplies schema compatibility only; it does not change the Retail source or authorize new Retail transactions.

## Runtime boundary

| Setting | Final UAT value |
|---|---|
| Identity | `platform_core` |
| Restaurant service | `legacy` |
| Retail service | `retail` — pre-existing value, unchanged by WP50 |
| Takeaway service | `takeaway` — pre-existing value, unchanged by WP50 |
| Reference projectors | Platform and Retail enabled |
| Company Kitchen writes | `false` |
| Company Distribution writes | `false` |
| UAT authentication bypass | `false`; auto-login endpoint returned `404` |

No routing, source-of-truth, Production flag, live payment provider, real tax or Takeaway/Central write boundary changed.

## Automated evidence

- Full backend regression: PASS — 453 tests, 1 skipped.
- WP50 API smoke: PASS on UAT.
- Idempotent open, cash movement and close replay: PASS; no duplicate business row or journal entry.
- Under-threshold and manager-approved movement paths: PASS.
- Variance approval, stale-version rejection and close blocker: PASS.
- Immutable close snapshot, audit count and accounting journal reconciliation: PASS.
- Main and Retail migrations: local upgrade/downgrade/upgrade PASS; final UAT heads confirmed above.
- Frontend TypeScript and production/PWA build: PASS; existing large-chunk advisory only.

## Formal-role evidence

All four accounts used the normal login and `/auth/me` paths. Server-held passwords were never written to Git or evidence. The temporary browser password was rotated back to the Server-held secret after testing.

| Role | Open / close / handover | Cash movement | Approve movement / variance | Result |
|---|---:|---:|---:|---|
| Cashier | Yes | Create | No | PASS |
| Branch Manager | Yes | Create | Yes | PASS |
| Accountant | No | No | No | PASS; finance role cannot operate a Cashier shift |
| Purchasing | No | No | No | PASS; purchasing role cannot operate or approve a Cashier shift |

Because UAT deliberately remains on the transitional `RESTAURANT_SERVICE_DATABASE=legacy` path, the four bounded formal-UAT user references were synchronized from Platform identity into the Legacy operational database before shift testing and again after password restoration. This was UAT reference preparation only; no identity routing or service cutover changed.

## Browser UAT

### Functional flow

- Paired temporary Counter `C-PFZKRY3HH9` and opened Staff shift `S20260921-001` with ฿500 opening float.
- Server summary began at version 1 and expected ฿500.
- Recorded an under-threshold ฿100 cash-in with reason; summary advanced to version 2, expected cash became ฿600 and the journal reconciled.
- Counted denominations, closed exactly and selected Staff handover.
- Staff authentication cleared and the browser returned to login while Counter pairing remained available for the next Staff member.
- A final post-fix shift `S20260921-003` opened with ฿1, counted ฿1 and closed with zero variance and handover.

### Tablet-landscape final check

At 1024×768 after the final frontend fix:

- document width equalled viewport width (`1024`); no page-level horizontal overflow;
- 70 visible buttons/inputs/selects were measured and none was below the 44×44px touch baseline;
- the shared dialog close control measured exactly 44×44px and exposed the label `ปิดหน้าต่าง`;
- open-shift, Server summary, denomination count, close and handover remained usable.

The offline mutation policy remains fail-closed through the existing WP47 client/Server contract and automated regression. No physical network-loss, printer, cash drawer or PromptPay pass is claimed here; those physical checks remain WP54.

### Cleanup

- No Staff shift was left open.
- All formal account passwords were restored from the Server-held UAT secret and the restored user references were synchronized to the transitional Legacy database.
- Temporary Counter device `254bf3af-f74d-4269-af09-6caca95f8d9f` was revoked with reason `WP50 browser UAT completed`.
- Browser viewport was reset and the temporary UAT tab was closed.

## Rollback rehearsal

WP50 contains financial/audit rows, so the rehearsal correctly used application-image rollback and retained the additive schema.

| Operation | Result |
|---|---|
| Roll back to `restaurant-pos-backend:wp48-486a259` + `restaurant-pos-frontend:wp49-9ff3e22` | PASS — 10 seconds; public health OK |
| Restore WP50 backend/frontend images | PASS — 10 seconds; public health and readiness OK |
| Final backend state | `restaurant-pos-backend:wp50-7af7a99`, healthy |
| Final frontend state | `restaurant-pos-frontend:wp50-63e8496`, running |

No database downgrade was attempted because preserving financial and audit evidence is mandatory.

## Production isolation

Production remained untouched and retained its pre-WP50 identities:

| Service | Image | Container ID |
|---|---|---|
| Backend | `restaurant-pos-backend:auth-a0fdccf` | `f6e08435721a` |
| Frontend | `restaurant-pos-frontend:ui-e4200ca` | `857e0dbab1a2` |
| Nginx | `restaurant-pos-nginx:unified-d528512` | `aea97e7f90f7` |
| Cloudflared | `cloudflare/cloudflared:2026.7.0` | `ae6862f8a09f` |
| PostgreSQL | `postgres:15-alpine` | `3565e3fd72ad` |
| Redis | `redis:7-alpine` | `76658d7ad2fd` |

Production deployment and activation remain **NO-GO**.
