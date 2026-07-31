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

Phase 1 is introducing explicit physical Control Plane and Restaurant database boundaries while the legacy database remains authoritative until a separately verified data cutover. See [Database Boundaries](./database-boundaries.md).
