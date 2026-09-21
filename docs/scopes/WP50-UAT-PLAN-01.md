# WP50 UAT Plan — Restaurant Shift Operations

Date: 2026-09-21
Environment: UAT only
Production: unchanged

## Deployment gate

1. Verify the Git remote, repository, branch and exact candidate commit.
2. Back up the UAT database and record current UAT/Production container identities.
3. Build immutable WP50 backend/frontend images from the candidate commit.
4. Upgrade only the Restaurant UAT main schema to `wp50shift0024`.
5. Keep Retail source, Takeaway/Central writes, live provider and real tax flags unchanged.
6. Start the UAT candidate and pass health/readiness checks.

## Automated UAT

- Run WP50 API smoke against UAT with isolated UAT users and branch data.
- Verify exact retries for open, cash movement and close do not duplicate data.
- Verify movement journal count, close audit count and immutable snapshot.
- Verify manager threshold approval and stale-version rejection.
- Verify a close blocker prevents close without partial mutation.

## Browser and role UAT

| Role | Expected result |
|---|---|
| Cashier | Open shift, view Server summary, record under-threshold movement, count cash, request approval and close/handover |
| Branch Manager | Approve threshold movement/variance and view complete audit evidence |
| Accountant | View finance/audit outcomes but cannot operate a Cashier shift without the bounded permission |
| Purchasing | Cannot operate or approve a Cashier shift unless explicitly assigned the permission |

Test Desktop 1440×900 and iPad landscape 1024×768. Verify Loading, Empty, Error, Offline, stale version, Permission denied and Approval required. Offline may display cached read state but must disable mutation, approval and close.

## Rollback evidence

- Validate the Alembic downgrade path locally before deployment.
- Rehearse UAT application-image rollback to WP49 frontend/WP48 backend.
- When WP50 financial/audit rows exist, do not downgrade the schema; retain additive columns/tables and roll back application images only.
- Restore WP50 candidate after rehearsal and re-run health/readiness.
- Confirm Production identities and flags are unchanged.

## Exit rule

The Phase Gate closes only after deployment identity, API smoke, role/browser evidence, rollback result and Production isolation are recorded in a separate UAT evidence document.
