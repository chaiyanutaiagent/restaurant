# Scope ID: P4-PHASE-GATE-06

สถานะ: **Verified — Phase 4 Restaurant ERP Core complete**

Phase: **Phase 4 — Restaurant ERP Core**

วันที่ตรวจ: **1 สิงหาคม 2026**

Business type: **restaurant**

Activation: **false — no production deploy, live migration, runtime cutover, APK, or push**

## Gate Coverage

- `P4-REPORT-SCOPE-01`: Company/Brand/Branch/Station report authorization
- `P4-DASHBOARD-COSTING-02`: dashboard reconciliation and auditable recipe costing
- `P4-SALE-HANDOFF-03`: transactional outbox and idempotent accounting handoff
- `P4-PRODUCTION-STAFF-04`: production entitlement and Employee-linked assignments
- `P4-RESTAURANT-ERP-ROUTING-05`: signed-context operational database routing

## Acceptance

- [x] Brand Manager sees only the assigned Brand aggregate
- [x] Branch/Station Manager cannot query another Branch
- [x] Recipe cost records source price, source reference, stock unit, normalized quantity, and conversion factor
- [x] One sale produces one Payment, stock movement set, durable event, and accounting journal
- [x] Restaurant operational outbox has no SQL foreign key to Platform/Retail/Takeaway
- [x] Aggregate sales and payment reconciliation exposes source sums and deltas
- [x] Production is disabled by default and requires Brand entitlement plus permission/scope
- [x] Operational staff assignment requires Active Employee evidence outside Company Owner scope
- [x] POS/Stock/Purchase/Transfer select the database only from signed server-owned context

## Verification Record

- Gate command: `scripts/rehearse-phase4-core.sh --yes`
- Legacy migration: `6b7c8d9e0f12` → `p4feature0006` → baseline → target
- Platform migration: `p1platform0003` → `p4platform0008` → baseline → target
- Restaurant migration: `p1restaurant0003` → `p4restaurant0005` → baseline → target
- Backend regression: 174 tests passed
- API smokes: sale handoff, staff scope, report scope, production batch, and recipe/inventory passed
- Frontend: TypeScript type-check and production/PWA build passed; existing chunk-size warning only
- Live source fingerprints unchanged; temporary Phase 4 database count after cleanup: `0`
- Main backend remained stopped
- `restaurant-pos-dev-backend:latest` remained
  `sha256:578dd5339c9ea6791d075384e4a2b92cd8422738b809cd147fd6e4eb364cc8de`
- Artifact:
  `/private/tmp/restaurant-p4-artifacts/p4-core-gate-06-20260801T105426Z/manifest.txt`

## Rollback

1. Keep the new production entitlement disabled.
2. Revert the Phase 4 implementation commits.
3. Downgrade only the additive Legacy/Platform/Restaurant Phase 4 migrations if they were applied later.
4. Preserve Sale/Payment/StockMovement, outbox, production, and assignment history during any runtime rollback.

Phase 5 may begin only by explicit Platform Owner instruction; this gate does not activate production.
