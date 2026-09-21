# WP52 Phase Gate — Restaurant Exceptions and Receipt Center

Date: 2026-09-21
Local engineering: **PASS**
UAT API/rollback: **PASS**
UAT visual: **PARTIAL — paired-Counter actions pending**
Production: **NO-GO / unchanged**

## Accepted so far

- Server-authoritative Price/Discount, Restaurant Cancellation/Waste/Audit and Refund/Tax contracts.
- Dedicated Discount workspace and Manager approval context.
- Two-pane Bill & Receipt Center composition with safe Void/Refund routing and Exchange disabled.
- Legacy full/partial Refund Client paths removed; UAT simulator build-gated and Production default off.
- Direct online WAP/Store endpoints cannot bypass the signed Offline Sync envelope.
- Desktop/iPad POS and Discount presentation.
- Immutable UAT release, application-only rollback and Production isolation.

## Required before closure

1. Explicitly authorize creating or rotating one UAT-only Counter pairing credential for the current test browser.
2. Open a Staff shift through the normal paired-device flow.
3. Complete formal browser checks for Bill Center search/filter/detail, eligible/ineligible Void,
   cancellation preview and Manager approval, Refund quote/recovery and receipt/tax non-fiscal state at
   1440×900 and 1024×768.
4. Record the result and close the registry rows D24–D28 and D32 only after those checks pass.

Physical printer, cash drawer, PromptPay terminal and real network-loss tests remain WP54 and are not a
WP52 pass claim. Production, live providers, real tax documents, Retail source changes and
Takeaway/Central Kitchen writes remain unauthorized.

Detailed evidence: [WP52-UAT-EVIDENCE-04.md](./WP52-UAT-EVIDENCE-04.md)

## Decision

WP52 remains open. Engineering and Server-contract risk are cleared, but the paired-Counter browser
acceptance gate must be completed before WP53 begins as an accepted package.

