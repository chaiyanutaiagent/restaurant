# WP51 Phase Gate — Restaurant Hold Draft and Order Center UX

Date: 2026-09-21
Local engineering: **PASS**
UAT: **PASS**
Production: **NO-GO / unchanged**

## Accepted scope

- Server-backed Hold Draft workspace with Branch-wide visibility, explicit ownership, Counter/shift/location
  provenance, lifecycle history and permission-aware actions.
- Safe create, claim, resume, release, discard, reassign and reopen behavior using idempotency and versions.
- Explicit cart-replacement, conflict and price/availability revalidation flows; no automatic merge or overwrite.
- Restaurant Order Center with canonical session/source/status filters, operational list/detail workspace,
  kitchen progress and real navigation back to the existing order/checkout path.
- Loading, empty/no-result, error, offline/stale and permission-aware presentation without creating a
  second order or financial source of truth.
- Desktop and iPad landscape touch/layout baseline.

## Evidence

- Implementation: `b1a2701`.
- UAT smoke alignment: `3a398bd`.
- Detailed evidence: [WP51-UAT-EVIDENCE-04.md](./WP51-UAT-EVIDENCE-04.md).
- UAT final images: `restaurant-pos-backend:wp51-b1a2701` and
  `restaurant-pos-frontend:wp51-b1a2701`.
- Corrected app-only rollback to WP50 and restoration to WP51 each completed in 11 seconds with public
  health/readiness passing.
- Production image/container identities remained unchanged.

## Boundaries retained

- No Production deployment or flag activation.
- No Takeaway/Central Kitchen transaction activation.
- No Retail source change.
- No live payment-provider action or real tax/credit-note issuance.
- No physical printer, cash drawer, PromptPay or real network-loss pass is claimed; those remain WP54.
- `docs/ux-ui/` remains reference-only and was not staged or changed.

## Decision

WP51 is closed for Local/UAT. D20–D23 and D29 are accepted as implemented against the current Server
contracts. WP52 may begin in Local/UAT to compose cancellation, discount, approval, refund and receipt
UX on WP43/WP45/WP46; this does not authorize Production or any live provider/tax action.
