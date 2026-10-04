# WP10-WP15 — Multi-business UAT Activation

Status: **UAT activated; physical UAT deferred; Production not activated**  
Execution date: `2026-09-16`  
Target: `https://uat-pos.foodchainservice.com`  
Branch: `codex/foodchainservice-platform`

## 1. Scope and decision

This work package activates the Takeaway and Retail boundaries in UAT, connects both to the
Platform-owned Shared ERP reporting contract, rehearses the Chambo import, and proves that the
five-database backup can be restored in an isolated environment.

It does not authorize a Production cutover. Physical iPad, scanner, printer, cash-drawer, offline,
customer QR, accountant, and owner-acceptance tests remain deferred by the owner.

## 2. Work-package outcome

| WP | Outcome | UAT evidence |
|---|---|---|
| WP10 — Takeaway UAT | Activated the dedicated Takeaway database and UAT workspace. Seeded food, drink, dessert, and special menus plus opening stock. | Paid order `TW-20260916-1F3972-0001`, total `73.83`, reached Shared ERP. |
| WP11 — Chambo rehearsal | Ran the Chambo import contract transactionally without modifying `/Users/user/Projects/erp-pos-run`. Replay remained idempotent. | `10` records, opening stock `50.0000`, opening credit `1500.00`, replay passed. |
| WP12 — Takeaway + Shared ERP | Verified catalog, paid order, stock/refund behavior, public QR ordering, pickup, kitchen, central-order/transfer acknowledgement, and shared-stock isolation across Brands. | Takeaway report: `1` order, net `73.83`, tax `4.83`; transactional smoke passed. |
| WP13 — Retail UAT | Completed selective migration/parity, then switched only UAT to the Retail database. | Sale `SO20260916-0001`, total `107.00`; Retail stock changed `20 -> 19` while Legacy remained `20`. |
| WP14 — Cross-system reporting | Verified Restaurant, Retail, and Takeaway facts in the Platform reporting database and healthy independent source cursors. | Restaurant `69.00`, Retail `107.00`, Takeaway `73.83`; `3` restored reporting facts. |
| WP15 — Production readiness | Extended migration, validation, backup, and restore operations to Legacy + Platform + Restaurant + Retail + Takeaway. Performed an isolated restore drill and removed the temporary restore stack afterward. | Five restored boundaries matched; table counts `141/41/127/29/34`; business data and reporting facts were present. |

## 3. UAT runtime state

- Identity database: `platform_core`
- Restaurant runtime: `legacy` during the controlled transition
- Retail runtime: dedicated `retail` database
- Takeaway runtime: dedicated `takeaway` database
- Platform reference projector: enabled
- Retail reference projector: enabled
- Shared reporting projector: enabled
- Takeaway feature: enabled
- Production backend remains on image `restaurant-pos-backend:4c1c2ba`

The UAT backend is healthy with zero restarts. Internal `/health` and `/health/ready`, public `/`, and
public `/pos` passed after the activation and restore drill.

## 4. Safety and recovery evidence

Pre-activation backup:

`/home/behappyaiagent/backups/restaurant-uat-wp10-15/pre-activation-20260916T092216Z`

Post-activation five-database backup:

`/home/behappyaiagent/backups/restaurant-uat-wp10-15/post-activation/restaurant-pos-prod-20260916T094027Z`

Both backups contain database dumps plus uploads and Redis artifacts with SHA-256 verification. The
post-activation backup was restored into the isolated Compose project
`restaurant-wp15-restore-20260916`. Restored boundaries were:

| Database | Boundary | Restored public tables |
|---|---|---:|
| Legacy | legacy | 141 |
| Platform | platform_core | 41 |
| Restaurant | restaurant | 127 |
| Retail | retail | 29 |
| Takeaway | takeaway | 34 |

The restore drill found a PostgreSQL first-start race: readiness could pass while the image was still
restarting after initialization. Commit `ff9c47e` now waits until the final PostgreSQL process owns PID 1
before restore begins. The second restore completed successfully. The isolated stack and its volumes
were then removed; the retained backup was not deleted.

## 5. Reporting corrections found during UAT

- Commit `e2f39be` preserves the initial source state when the first event for a source is malformed,
  preventing unrelated later source streams from being blocked by transaction rollback.
- Commit `8c6371e` resolves Legacy reporting Brand/Branch dimensions from Platform references while
  identity ownership is in transition.
- The one UAT dead-letter event was redriven explicitly after the correction. All four reporting source
  states — Legacy, Restaurant, Retail, and Takeaway — ended healthy with zero failures.

## 6. Acceptance evidence

- UAT preparation is idempotent and protected by environment, hostname, confirmation, and identity
  guards.
- Platform projection applied without failures.
- Retail selective migration table counts and digests matched.
- Takeaway import and operational replay were idempotent.
- Retail and Takeaway wrote only to their dedicated operational databases.
- Shared ERP received one completed fact from each Restaurant, Retail, and Takeaway flow.
- Five-database backup checksums and dump catalogs passed.
- Five-database isolated restore passed and retained business data.
- UAT and Production containers remained healthy; Production image and data were not changed.

## 7. Rollback order

1. Disable new writes and stop UAT activity.
2. Route Retail UAT back to `legacy`.
3. Disable Takeaway and shared reporting projectors if their behavior is under investigation.
4. Re-deploy the previous reviewed UAT backend image.
5. Restore the pre-activation backup only when data rollback is required and approved.
6. Re-run boundary, health, source-state, and smoke checks.

Do not perform destructive restore against Production without an explicit backup directory, approval,
and recorded go/no-go decision.

## 8. Remaining gates before Production

- Restaurant physical iPad/Safari flow, table opening, customer QR, KDS, payment, receipt, and stock
  confirmation
- Takeaway public QR/pickup/kitchen flow on target devices
- Retail scanner, printer, cash drawer, offline/reconnect, and receipt flow
- Tax/accounting review using representative supplier and filing data
- Operator monitoring, backup retention, incident ownership, and rollback handoff
- UAT sign-off, security acceptance, owner go/no-go, DNS/TLS cutover plan, and Production release approval

Until these gates are signed off, the correct state is **UAT available for testing; Production blocked**.

## 9. Change set

- `5202083` — prepare Takeaway and Retail UAT workspaces
- `4f7faf1` — complete five-database Production recovery tooling
- `e2f39be` — retain reporting source state on first failure
- `8c6371e` — resolve Legacy reporting dimensions from Platform
- `ff9c47e` — wait for final PostgreSQL startup before restore

