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
- Added additive Retail boundary migrations `p10retail0004` and `p11retail0005` for persistent Server-authoritative pricing quotes and the bounded POS pricing/Sale/Payment compatibility columns. The migration chain was rehearsed upgrade → downgrade → upgrade on an isolated PostgreSQL database.
- Disabled Retail Hold Draft queries and controls until WP57 so the Retail shell cannot call the not-yet-migrated `pos_hold_drafts` contract.
- Disabled the Retail Return/Refund workspace and every mutating Refund API with the explicit `retail_return_not_ready` fail-closed response until WP57. Bill lookup, receipt viewing and printing remain available.

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
| Focused Retail/Pricing/Shift tests | PASS — final WP55/WP56 contract set 21/21; earlier Retail/Pricing set 53/53 |
| Full backend regression | PASS — 493/493 |
| Schema/migration | PASS — `p10retail0004` → `p11retail0005`, upgrade → downgrade → upgrade; Hold Draft tables intentionally absent |
| Production flags/data source | Unchanged |

## UAT acceptance

1. [x] Provision the bounded Retail UAT identity without storing credentials in source or evidence.
2. [x] Verify signed Retail Catalog, SKU/barcode and persistent unknown/out-of-stock exception states in the authenticated UAT browser.
3. [x] Verify customer masking contract and that Loyalty remains disabled.
4. [x] Complete one controlled cash-only UAT sale and confirm Server price, stock, consumed quote and outbox evidence.
5. [x] Verify non-cash/offline checkout, Retail Hold and Retail Return/Refund fail closed.
6. [x] Verify Bill Center and receipt UI without claiming printer/cash-drawer physical pass.
7. [x] Record immutable image identities, app-only rollback/restore and Production before/after identities.
8. [x] Complete independent QA retest, then disable the bounded persona and revoke its sessions/assignments.
9. [ ] Complete physical tablet, scanner, printer, cash drawer and network-loss UAT.

WP56 implementation, authenticated software UAT and independent QA are complete. The phase remains conditional pending physical device/network acceptance; no Production readiness is claimed. Detailed evidence is in `WP56-UAT-EVIDENCE-02.md`.
