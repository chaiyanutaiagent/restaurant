# WP48 Phase Gate

Date: 2026-09-21  
Decision: **UAT PASS — PHASE GATE CLOSED**

## Gate A — Scope and contract

- Restaurant POS catalogue source is server-bounded by signed Restaurant Brand/Branch context.
- Client-supplied product filters cannot widen `restaurant_menu` to raw/Retail/non-saleable products.
- Category de-duplication preserves products attached to every legacy duplicate ID.
- Shared design tokens and system states do not alter WP42–WP47 business outcomes.
- Formal UAT users use canonical role presets; auth bypass cannot coexist with the preparation command.

Result: **PASS**.

## Gate B — Local engineering

- Backend regression: 444 passed, 1 skipped.
- WP48 focused tests: 21 passed.
- Frontend TypeScript: pass.
- Frontend production/PWA build: pass, with the existing large-chunk advisory.
- Python syntax: pass.
- Database migration: N/A; no schema change.

Result: **PASS**.

## Gate C — UAT

- Immutable candidate `486a259` was deployed only to the `restaurant-pos-uat-drill` stack.
- UAT application images are `restaurant-pos-backend:wp48-486a259` and `restaurant-pos-frontend:wp48-486a259`; their immutable image IDs are recorded in `WP48-UAT-EVIDENCE-03.md`.
- Runtime inspection confirmed `UAT_AUTH_BYPASS_ENABLED=false` and `IDENTITY_DATABASE=platform_core`.
- Cashier, Branch Manager, Accountant and Purchasing identities passed real login, role landing and Restaurant catalogue checks. The temporary Cashier password used for browser UAT was restored through the bounded UAT command after the check.
- Restaurant POS returned 28 allowed menu items in 7 unique categories; raw/Retail catalogue leakage was not observed.
- Company and POS surfaces were checked at 1440×900 and 1024×768. There was no horizontal viewport overflow and visible interactive targets met the 44px baseline.
- Company context, Action Center, Product readiness and Device/Sync state were present; Hotel PMS remained hidden from the current product shell.
- App-only rollback from WP48 to WP47 completed in 11 seconds and restore to WP48 completed in 13 seconds; health and formal-role smoke checks passed after restore.
- Production container identities and start times were unchanged before and after the drill.

Result: **PASS**. WP49 may start under the existing Local/UAT-only authorization.

## Production decision

**NO-GO.** Production deployment, migrations, data-source changes and feature activation remain unauthorized. Closing WP48 does not alter that boundary.
