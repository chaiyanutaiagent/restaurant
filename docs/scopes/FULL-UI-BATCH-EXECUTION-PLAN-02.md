# Foodchainservice Full UI — Fast-track Batch Execution Plan

Date: 2026-09-22  
Environment: Local and UAT only  
Production: unchanged and not authorized

## Operating model

Each WP receives a short scope delta, implementation, affected contract/security tests, targeted type-check when needed, a dedicated commit/push, and a registry checkpoint.

At the end of each Batch, Engineering runs one combined gate covering full type-check/build, backend regression, role/tenant/permission matrix, Loading/Empty/Error/Offline/Stale states, Desktop/Tablet/Touch, immutable UAT deployment, Production identity before/after, rollback/restore, and combined evidence.

The following hard gates cannot be deferred: tenant/role isolation, Server authority, permission, idempotency/concurrency, payment/refund/tax/stock mutations, schema/migration, secrets, and real-data risk.

## Batch plan

| Batch | Work Packages | Scope | Current state |
|---|---|---|---|
| A | WP55–WP58 | Retail POS R01–R10: foundation, scan-first sale, exceptions, payment/receipt, Hold/Return/Shift, offline and Counter readiness | WP55 authenticated Retail checkpoint passed; WP56 software UAT and rollback passed, independent QA/physical UAT pending; WP57–WP58 planned |
| B | WP59–WP61 | Platform Console, Company Admin and Shared ERP | Planned |
| C | WP62–WP64 | Takeaway, Central Kitchen/Supply Chain and Public Customer Experience | Planned; write actions remain gated where contracts/readiness are absent |
| D | WP65 | Integration, Reporting, Reconciliation, Release Governance and final full-system UAT | Planned |

## QA lane

QA may begin WP48–WP53 against the immutable accepted UAT build recorded by the relevant phase gate. WP54 may be inspected, but must not receive QA sign-off until the physical candidate is frozen and the remaining hardware/network evidence is attached.

The QA access matrix uses test-only UAT accounts for Company Owner/Admin, Branch Manager, Cashier/Service, Kitchen and Auditor. Passwords, tokens and secrets must never be stored in the repository, evidence documents, screenshots or chat.

Every defect record must include build/commit, date, device/viewport, role, Company/Branch/Counter, reproduction steps, expected/actual result, screenshot or video, severity, related WP and required test-data cleanup.

## Fixed restrictions

- No Production deployment or Production feature flags.
- No live provider transaction or real tax document.
- No Chambo real-data mutation.
- No Retail Production source cutover.
- No Takeaway or Central Kitchen write activation without a later explicit gate.
- Design references under `docs/ux-ui/` remain user-owned and are never staged by Engineering.
