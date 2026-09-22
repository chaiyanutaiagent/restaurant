# WP52 Phase Gate — Restaurant Exceptions and Receipt Center

Date: 2026-09-22
Local engineering: **PASS**
UAT API/rollback: **PASS**
UAT paired-Counter visual: **PASS**
Production: **NO-GO / unchanged**

## Accepted

- Server-authoritative Price/Discount, Restaurant Cancellation/Waste/Audit and Refund/Tax contracts.
- Dedicated Discount workspace and Manager approval context.
- Two-pane Bill & Receipt Center composition with safe Void/Refund routing and Exchange disabled.
- Legacy full/partial Refund Client paths removed; UAT simulator build-gated and Production default off.
- Direct online WAP/Store endpoints cannot bypass the signed Offline Sync envelope.
- Desktop/iPad POS and Discount presentation.
- Normal UAT Counter pairing and Staff-shift context.
- Bill Center search/filter/detail and receipt rendering.
- Safe eligible/ineligible Void routing without executing the test Void.
- Cancellation preview, recipe Waste disclosure and Manager maker-checker without changing the sample order.
- Refund Server quote, Sandbox/non-fiscal states and Manager maker-checker without executing the refund.
- Desktop and iPad-landscape composition for the exception surfaces.
- Immutable UAT release, frontend rollback/restore and Production isolation.

## Closure evidence

1. `UI-DEVICE-01` was rotated and paired through the normal one-time UAT flow.
2. The paired Counter accepted Staff shift `FB20260922000741` with the expected Branch and warehouse.
3. Two synthetic UAT receipts exercised settled Refund routing and the eligible Void form. The only
   direct fixture change was an `authorized` payment state used for visual verification; it was restored
   to its original `unknown` value immediately afterward.
4. Bill Center, Void, Cancellation, Manager approval, Refund quote and receipt/non-fiscal states passed
   at the normal desktop viewport and the critical Bill Center/Refund surfaces passed at 1024×768.
5. Frontend-only rollback and restore each completed in 1 second; public health passed, final 15-minute
   UAT 5xx count was zero and all Production container identities remained unchanged.

Physical printer, cash drawer, PromptPay terminal and real network-loss tests remain WP54 and are not a
WP52 pass claim. Production, live providers, real tax documents, Retail source changes and
Takeaway/Central Kitchen writes remain unauthorized.

Detailed evidence: [WP52-UAT-EVIDENCE-04.md](./WP52-UAT-EVIDENCE-04.md)

## Decision

**WP52 UAT PHASE GATE CLOSED.** WP53 may begin under the existing Local/UAT-only authorization.
Production deployment, live providers, real tax documents, Retail source changes and
Takeaway/Central Kitchen transactions remain outside this decision.
