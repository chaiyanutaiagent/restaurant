# WP56 — Retail Product Exceptions, Cart, Customer, Payment and Receipt

Date: 2026-09-22
Environment: Local and UAT only
Design coverage: Retail R03–R05
Production: unchanged and not authorized

## Scope delta

WP56 moves Retail product selection from Client assumptions to an online Server-authoritative lookup and quote. It adds persistent exception recovery, Variant selection, safer customer presentation and a deliberately narrow Cash Pilot checkout.

## Implemented

### R03 — Product exception states

- Added signed Retail lookup by exact barcode or case-insensitive SKU.
- Enforced Company, Brand, Branch and active Stock Location boundaries on the Server.
- Excluded Restaurant menu items and raw materials from Retail lookup.
- Returned explicit `matched`, `not_found`, `variant_required` and `unavailable` states.
- Detected ambiguous codes and failed closed instead of choosing a product.
- Returned Server price, selected Variant and available stock for the active Location.
- Added persistent, touch-sized recovery states for unknown code, Variant required, unavailable stock, stock limit, price change, permission/context failure and Server error.

### R04 — Cart, customer and discount

- Cart lines retain the selected Variant, Server-authoritative price and price-version evidence.
- Every Retail line is quoted by the Server before addition; final checkout is quoted again.
- Price drift requires an explicit `ใช้ราคา Server` action and never silently trusts stale Client price.
- Customer phone numbers are masked in Retail search and selected-customer surfaces.
- Retail Loyalty redemption is disabled until an atomic Reserve → Commit/Release Server contract exists. No points are deducted by this package.

### R05 — Payment and receipt

- Retail Pilot enables cash only.
- PromptPay, card, transfer, split payment and provider paths remain visible only as disabled readiness states.
- The Server independently rejects Retail non-cash and offline/sync checkout, even if a Client is modified.
- The checkout action clearly identifies cash confirmation and requires online, signed context and a trusted Retail Catalog.
- Receipt presentation remains available, while printer and cash-drawer status explicitly remain unverified physical UAT.

## Security and regression hardening

- Added a bounded UAT-only administrator password-rotation command with HTTPS `uat-*`, development-environment, Platform identity, auth-bypass-off and explicit confirmation guards.
- The command reads the new password only from environment, revokes refresh tokens and writes an audit entry.
- Added a separate bounded `uat.retail-cashier` persona command. It derives the canonical Cashier permission preset, resolves exactly one active Retail UAT Brand/Branch, writes signed `retail_pos` context, maps that UAT storefront to the isolated `UI-MAIN` showcase location with audit evidence, and can disable the user and revoke its sessions after QA.
- Fixed the clean Docker regression fallback so runner-contract tests receive the repository `/scripts` directory.

## Intentional deferrals

- Atomic Loyalty reservation/commit/release.
- Live PromptPay/card/transfer provider and reconciliation.
- Real tax invoice or credit note.
- Physical printer, cash drawer, scanner and terminal acceptance.
- Retail offline authorization lease and encrypted outbox policy.
- Retail Production data-source cutover.

## Engineering gate

| Check | Result |
|---|---|
| Python 3.12 compile | PASS |
| Frontend type-check | PASS |
| Focused WP55–WP56 tests | PASS — 16/16 |
| Full backend regression | PASS — 486/486 before two final focused credential-guard cases; final focused suite 16/16 |
| Schema/migration | None |
| Production flags/data source | Unchanged |

## UAT acceptance still required

1. Provision the bounded Retail UAT identity without storing credentials in source or evidence, then disable it and revoke sessions after the QA round.
2. Verify signed Retail Catalog, SKU/barcode, Variant and all persistent exception states on Desktop and tablet.
3. Verify customer masking and that Loyalty cannot mutate points.
4. Complete one controlled cash-only UAT sale and confirm Server price/stock/idempotency evidence.
5. Verify non-cash, offline, unsigned and cross-tenant requests fail closed.
6. Verify receipt UI without claiming printer/cash-drawer physical pass.
7. Record immutable image identities, rollback/restore and Production before/after identities.

WP56 implementation is complete at the Local Engineering Gate. UAT, rollback and authenticated Retail acceptance remain open; no Production readiness is claimed.
