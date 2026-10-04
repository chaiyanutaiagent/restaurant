# WP48 — UAT Cleanup and Shared Design System Baseline

Date: 2026-09-21  
Environment: Local and UAT only  
Production: unchanged; deployment and flags are not authorized

## Objective

Make the existing WP42–WP47 surfaces safe and visually consistent enough to become the baseline for WP49–WP58 without changing their business outcomes.

## Implemented scope

### Restaurant POS catalogue boundary

- Added the server-owned `catalog_scope=restaurant_menu` query mode.
- The server ignores conflicting client product filters for this mode and requires a signed Restaurant Company/Brand/Branch context.
- The resulting catalogue is limited to active, saleable `menu_item` products for the signed Brand plus intentionally Company-wide menu items.
- Raw materials, Retail products, non-saleable records and unrelated test records cannot enter the Restaurant POS through this query mode.
- Barcode/SKU lookup uses the same bounded source.
- Offline catalogue rows are filtered again in the POS as defense in depth.
- Duplicate category labels are grouped by normalized Thai name while preserving every underlying category ID, so selecting the group still returns products from legacy duplicate category records.

### Shared UI baseline

- Promoted the approved Brand, surface, text, semantic, radius, focus and typography values into shared CSS/Tailwind tokens.
- Added a shared `SystemState` component covering Loading, Empty, No results, Error, Offline, Stale, Permission denied and Read-only.
- The state component uses icon + text + color, accessible alert/status semantics, reduced-motion support, optional freshness/reference evidence and a safe retry/action slot.
- Existing Company state presentation now delegates to the shared component.
- Existing minimum 44px touch target, focus visibility, responsive shell and data-table behavior remain the baseline.

### Formal UAT identity boundary

- Added an idempotent UAT-only command to prepare Cashier, Branch Manager, Accountant and Purchasing identities from the canonical role presets.
- The command refuses Production/non-`uat-*`, refuses to run while auth bypass is enabled, requires explicit confirmation and receives passwords only through environment variables.
- It never prints passwords and provides a bounded disable/rollback mode.
- UAT runtime must set `UAT_AUTH_BYPASS_ENABLED=false` before this command and formal permission/security UAT.

## Server authority and security

- Company and Brand are never accepted from a catalogue query parameter.
- Restaurant context is read from the signed access token.
- Permission enforcement remains `inventory.product.view` at the API boundary and WP43–WP47 server authority is unchanged.
- No schema migration is required.
- No Production data source, feature flag, payment provider, tax provider or Central Kitchen/Takeaway write state is changed.

## Automated evidence

| Check | Result |
|---|---|
| WP48 catalogue/UAT guard tests | 6 passed |
| Full backend unit regression | 444 passed, 1 skipped |
| Frontend TypeScript | passed |
| Frontend production/PWA build | passed |
| Python syntax compilation | passed |
| Git whitespace check | required before commit |

The Vite build reports the existing large-chunk advisory; it is not introduced as a WP48 functional regression and remains a performance backlog item for route-level code splitting.

## UAT acceptance

1. Deploy the immutable WP48 application candidate to UAT only.
2. Set `UAT_AUTH_BYPASS_ENABLED=false` and recreate only the UAT backend.
3. Prepare bounded real-role test users without exposing passwords in Git/logs.
4. Confirm login and landing for Cashier, Branch Manager, Accountant and Purchasing.
5. Confirm direct API denial for missing/non-Restaurant context.
6. Confirm Restaurant POS shows no raw material, Retail or approval-test products and no duplicated category labels.
7. Inspect Company and POS surfaces at 1440×900 and 1024×768 for focus, touch target and horizontal overflow.
8. Rehearse app-only rollback and confirm Production container identities/flags are unchanged.

## Rollback

- Application rollback: restore the previous WP47 UAT backend/frontend images.
- Identity rollback: run the bounded command with `--disable --yes`; it deactivates only the four `uat.*` identities and revokes their active company assignments.
- Configuration rollback for troubleshooting may re-enable the prior UAT bypass only as a temporary single-tester mode; it cannot be used for formal security sign-off.

## Explicit non-actions

- No Production deployment or migration.
- No Retail Legacy cutover.
- No Takeaway/Central Kitchen Production write activation.
- No Chambo real-data access.
- No live provider call or real fiscal document.
- No edit or commit under `docs/ux-ui/`.
