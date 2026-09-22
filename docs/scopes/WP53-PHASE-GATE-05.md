# WP53 Phase Gate — Restaurant Offline and Sync Recovery UX

Date: 2026-09-22  
Local engineering: **PASS**  
UAT shell/context/responsive/rollback: **PASS**  
Stateful network-loss UAT: **OPEN — carried into WP54**  
Production: **NO-GO / unchanged**

## Accepted

- Real encrypted Restaurant outbox drives the Sync Center.
- Company/Branch/Counter/Shift/Cashier and Network context.
- Pending, syncing, acknowledged, unknown, review, rejected, quarantined and reconciled presentation.
- Unknown inquiry and retry identity safety preserved from the WP47 contract.
- Cash-only offline limitation and online-only exception actions are stated correctly.
- Paid evidence has no operator discard action.
- Restaurant Takeaway POS badges route unresolved work to the Sync Center.
- Desktop/tablet composition, empty state, paired-Counter context and frontend rollback/restore.

## Gate still open

WP53 cannot claim a complete stateful UAT pass until a controlled real-network test produces and
observes at least one pending row, one lost-acknowledgement/inquiry path and one manager-review path.
Those tests require the same physical controls already assigned to WP54 and will be executed there
without weakening the Outbox or adding Production test hooks.

Detailed evidence: [WP53-UAT-EVIDENCE-04.md](./WP53-UAT-EVIDENCE-04.md)

## Decision

**WP53 implementation accepted; stateful UAT gate remains open and is carried into WP54.** WP54 may
begin on UAT. Production deployment, Production flags, live providers, real tax documents, Retail
source changes and Takeaway/Central Kitchen writes remain unauthorized.

