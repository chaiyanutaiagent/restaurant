# Restaurant POS Architecture Overview

Restaurant POS is organized as a core ERP platform with operational modules layered underneath it.

## System Shape

```text
ERP Core Platform
├─ ERP Admin
├─ POS Module
│  ├─ POS Workspace
│  └─ POS Admin
├─ Restaurant Module
│  ├─ Restaurant Workspace
│  └─ Restaurant Admin
└─ Integration Layer
```

## ERP Core Responsibilities

- Company, branch, user, role, and permission management
- Product catalog, inventory, accounting, tax, purchase, logistics, and reports
- Shared API key, webhook, external order, and audit foundations
- Shared data ownership rules for operational modules

## Operational Module Responsibilities

POS handles cashier operations, shifts, sales, payments, receipts, refunds, and POS-specific reporting.

Restaurant handles dining tables, dining sessions, QR menu ordering, kitchen tickets, pickup queue, recipes, and F&B-specific reporting.

## Integration Layer Responsibilities

- API keys and scopes for external systems
- Public API endpoints for product, stock, and order exchange
- Incoming signed webhooks from systems such as `poolproject`
- Outbound webhooks for Restaurant POS events
- External IDs and source names for idempotent synchronization

## Direction

ERP stays the core platform. POS and Restaurant stay below ERP as modules. External systems integrate through APIs and webhooks rather than sharing code or database tables directly.

Phase 1 established and locally verified explicit physical Control Plane and Restaurant database boundaries, reference projection, bounded runtime canaries and tenant/business-type isolation. Phase 2 then verified versioned role presets, Company/Brand/Branch/Station assignments, Kitchen privilege boundaries and Manager approval enforcement for discount, void, refund and stock operations. Phase 3 now has an Identity-owned, Branch/Station-bound device registry, pairing/revoke lifecycle, dedicated Counter/Kitchen/Pickup browser workspaces, and expiring signed offline-sale authorization. Counter requires both device and staff identity, while offline acknowledgements preserve the cashier, Branch, shift, location and optional Counter-device boundary. Device pairing uses a server-issued Device ID instead of a MAC address, persists a revocable refresh credential in Android Keystore-backed storage, and renews short-lived access automatically across app restarts. Each cashier shift records its staff operator, and the handover flow closes and audits the outgoing shift before logging out only the staff session. The remaining gate is tablet visual confirmation. The runtime stays on rollback-safe legacy defaults until a separately approved production activation. See [Database Boundaries](./database-boundaries.md), [Phase 2 Gate](../scopes/P2-PHASE-GATE-04.md), [Phase 3 Device Pairing](../scopes/P3-DEVICE-PAIRING-01.md), [Counter Staff Handover](../scopes/P3-COUNTER-STAFF-HANDOVER-04.md), [Durable Device Credential](../scopes/P3-DURABLE-DEVICE-CREDENTIAL-05.md), and [Offline Architecture](./restaurant-android-offline.md).
