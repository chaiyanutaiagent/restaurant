# Foodchainservice Full UI Implementation Registry

Date: 2026-09-22
Authority: tracked CTO program registry
Design source: `docs/ux-ui/` (reference only; never edited or committed by Engineering)
Production: unchanged and not authorized

## Purpose

This registry reconciles the approved 54-image UX/UI handoff with the Work Package sequence actually used by Engineering. It supersedes the proposed post-WP47 numbering only; it does not change any closed Phase Gate or Server contract.

The filesystem contains 55 PNG files. `customer-company/05-customer-company-action-center.png` is superseded by `05-customer-company-action-center-v2.png` and is excluded from the 54-image acceptance set.

## Status language

| Status | Meaning |
|---|---|
| Implemented | The intended operating flow is connected to current Server contracts and has a closed Local/UAT gate. |
| Adapted | A production-shaped flow exists, but the static composition was adapted to current routes/contracts. |
| Read-only | The surface can safely display Server data; write actions remain gated. |
| Disabled | The surface/action is intentionally visible but cannot mutate state because readiness or approval is missing. |
| Missing backend | The image proposes a state transition or data contract that does not yet exist safely on the Server. |
| Planned | Assigned to a real WP but not yet implemented. |
| In progress | The assigned WP is active. |

## Canonical Work Package sequence after re-sequencing

| WP | Area | State | Release boundary |
|---|---|---|---|
| WP42 | Customer Company Shell | Implemented; UAT gate closed | Production unchanged |
| WP43–WP47 | Price, Hold, Cancellation, Refund/Tax and physical-readiness foundations | Implemented/Adapted; package gates recorded | Live provider/physical owner sign-off still gated |
| WP48 | Shared design system and UAT cleanup | Implemented; UAT gate closed | Production unchanged |
| WP49 | Restaurant order entry, Table and QR | Implemented; UAT gate closed | Production unchanged |
| WP50 | Restaurant Shift Operations | Implemented; UAT gate closed | Production unchanged |
| WP51 | Restaurant Hold Draft and Order Center UX | Implemented; UAT gate closed | Production unchanged |
| WP52 | Restaurant Cancel, Discount, Refund, Receipt Center UX | UAT phase gate closed; paired-Counter browser, API and rollback passed | Sandbox/UAT only |
| WP53 | Restaurant Offline and Sync Recovery UX | Implemented on UAT; paired shell/rollback passed, stateful network gate carried to WP54 | Production unchanged |
| WP54 | Restaurant Counter Readiness and physical-UAT shell | Delivery gate closed; evidence shell, release identity and rollback passed | Physical checks remain open; Production unchanged |
| WP55 | Retail foundation and Scan-first sale | Authenticated Retail checkpoint passed | Legacy source unchanged |
| WP56 | Retail exceptions, cart/customer/discount and payment/receipt | Software Gate passed; physical acceptance remains HOLD | Cash Pilot only; Production/Legacy source unchanged |
| WP57 | Retail Hold/Resume, Return/Exchange/Void and Shift Operations | Software UAT and rollback passed; physical acceptance remains HOLD | Local/UAT only; Cash Pilot; Legacy identities fail closed |
| WP58 | Retail Offline Recovery, Counter Readiness and Retail Phase Gate | Software UAT gate closed; physical acceptance remains HOLD | No cutover/physical pass implied |
| WP59 | Platform Console identity, Team/RBAC and operator governance | In progress; Local checkpoint passed | UAT deployment pending; Platform Production unchanged |
| WP60 | Company Admin maturity, access review and Company audit | Planned | Tenant MFA/session decisions required |
| WP61 | Shared ERP operational and finance maturity | Planned | Real tax/provider/accountant gates remain |
| WP62 | Takeaway operational UI activation | Planned | Transactions remain gated until owner/canary approval |
| WP63 | Central Kitchen and Supply Chain UI activation | Planned | Read-only/dark-launch until stock/QC gates pass |
| WP64 | Public Customer Experience | Planned | Catalog/ecommerce owner decision required |
| WP65 | Integration, Reporting, Reconciliation and Release Governance | Planned | Provider/retention/owner gates remain |

Hotel PMS is out of scope and has no WP assignment.

## Fast-track batch execution

The execution contract is recorded in `FULL-UI-BATCH-EXECUTION-PLAN-02.md`. WP54 is closed at the delivery level with the physical acceptance gate intentionally open; Batch A may therefore begin without implying Production or hardware readiness.

| Batch | WP range | Checkpoint |
|---|---|---|
| A — Retail POS | WP55–WP58 | Combined software gate passed; physical/Production HOLD; Batch B may begin on Local/UAT |
| B — Platform/Company/ERP | WP59–WP61 | In progress at WP59 |
| C — Takeaway/Kitchen/Public | WP62–WP64 | Planned; unsafe writes remain gated |
| D — Governance/full-system UAT | WP65 | Planned |

## Image acceptance registry — Customer Company (10)

The superseded non-v2 Action Center file is not counted.

| # | Approved image | WP | Current state | Contract/readiness note |
|---:|---|---|---|---|
| C01 | `customer-company/01-customer-company-dashboard.png` | WP42 | Implemented | Company context, readiness, Action Center and device/sync summary are Server-backed. |
| C02 | `customer-company/02-customer-company-app-launcher.png` | WP42 | Implemented | Permission and product-readiness gates are separate. |
| C03 | `customer-company/03-customer-company-organization.png` | WP42/WP60 | Adapted | Current organization routes exist; maturity/audit work remains WP60. |
| C04 | `customer-company/04-customer-company-people-access.png` | WP42/WP60 | Adapted | Current user/role administration exists; access review and tenant MFA remain WP60. |
| C05 | `customer-company/05-customer-company-action-center-v2.png` | WP42 | Implemented | v2 is the canonical Action Center reference. |
| C06 | `customer-company/06-customer-company-erp-home.png` | WP42/WP61 | Adapted | Launcher/home exists; ERP maturity is WP61. |
| C07 | `customer-company/07-customer-company-restaurant-pos-home.png` | WP42/WP49–WP54 | Adapted | Restaurant launcher exists; operating surfaces are delivered sequentially. |
| C08 | `customer-company/08-customer-company-retail-pos-home.png` | WP42/WP55–WP58 | Adapted | Pilot/readiness shell only; Retail source cutover is not authorized. |
| C09 | `customer-company/09-customer-company-takeaway-home.png` | WP42/WP62 | Read-only | Takeaway engineering exists; write activation remains gated. |
| C10 | `customer-company/10-customer-company-central-kitchen-home.png` | WP42/WP63 | Read-only | Central Kitchen remains read-only/dark-launch. |

## Image acceptance registry — Design System and Restaurant (34)

| # | Approved image | WP | Current state | Contract/readiness note |
|---:|---|---|---|---|
| D01 | `design-system/01-foundations-component-board.png` | WP48 | Implemented | Shared tokens/components adopted. |
| D02 | `design-system/02-data-workspace-pattern-board.png` | WP48 | Adapted | Shared data workspace pattern exists across operational pages. |
| D03 | `design-system/03-document-form-and-approval-board.png` | WP43/WP45/WP46/WP48 | Adapted | Approval evidence is Server-authoritative; real tax/provider actions remain gated. |
| D04 | `design-system/04-full-receipt-tax-invoice-a4-v2.png` | WP46/WP52 | Adapted | Receipt/tax preview exists; real tax issuance remains gated. |
| D05 | `design-system/05-system-states-feedback-board.png` | WP48 | Implemented | Loading/Empty/Error/Offline/Stale/Permission states are shared. |
| D06 | `design-system/06-device-sync-integration-states.png` | WP41/WP48 | Implemented | Device/sync contract and status surfaces exist. |
| D07 | `design-system/07-permission-readiness-error-states.png` | WP37/WP42/WP48 | Implemented | Permission and readiness are independent fail-closed gates. |
| D08 | `design-system/08-responsive-layout-pattern-board.png` | WP48 | Implemented | Desktop/tablet patterns adopted. |
| D09 | `design-system/09-responsive-company-dashboard.png` | WP42/WP48 | Implemented | Company dashboard passed Desktop/tablet UAT. |
| D10 | `design-system/10-responsive-action-center-operational-status.png` | WP42/WP48 | Implemented | Action Center and operational status passed UAT. |
| D11 | `design-system/11-touch-pos-foundations-flow-board.png` | WP48 | Implemented | Touch baseline and POS shell adopted. |
| D12 | `design-system/12-restaurant-pos-order-entry.png` | WP49 | Implemented | 28-item signed Restaurant menu, category rail, cart and Server-priced submit passed UAT. |
| D13 | `design-system/13-restaurant-pos-table-modifier.png` | WP49/WP52 | Adapted | Table/session flow exists; quick options are unpriced notes until a priced-modifier contract exists. |
| D14 | `design-system/14-restaurant-pos-kds.png` | WP49 | Adapted | Server-backed KDS exists and received the WP49 Staff order. |
| D15 | `design-system/15-restaurant-pos-payment-receipt.png` | WP46/WP52 | Adapted | Current checkout/refund/receipt contracts exist; combined final UX is WP52. |
| D16 | `design-system/16-restaurant-pos-shift-flow-board.png` | WP50 | Implemented | Explicit Staff shift is distinct from Store sales-round closure and passed UAT. |
| D17 | `design-system/17-restaurant-pos-open-shift.png` | WP50 | Implemented | Server confirms Company/Branch/User/Location/Counter attribution and idempotency. |
| D18 | `design-system/18-restaurant-pos-close-shift.png` | WP50 | Implemented | Server summary, count, variance, blockers, immutable snapshot and audit passed UAT. |
| D19 | `design-system/19-restaurant-pos-staff-handover.png` | WP50 | Implemented | Handover clears Staff authentication while retaining Counter pairing; UAT passed. |
| D20 | `design-system/20-restaurant-pos-hold-order-flow-board.png` | WP51 | Implemented | Server-backed hold creation, explicit cart replacement and Order Center separation passed UAT. |
| D21 | `design-system/21-restaurant-pos-hold-bill-sheet.png` | WP51 | Implemented | Search/filter/sort, owner/Counter/shift/location, item detail and audit use the versioned Server contract. |
| D22 | `design-system/22-restaurant-pos-held-bills-resume.png` | WP51 | Implemented | Claim/resume/release/discard/reassign/reopen, revalidation and conflict handling passed API smoke. |
| D23 | `design-system/23-restaurant-pos-order-center.png` | WP51 | Implemented | Branch-scoped search/filter, canonical status/source and detail pane passed Desktop/tablet UAT. |
| D24 | `design-system/24-restaurant-pos-cancel-discount-refund-flow-board.png` | WP52 | Adapted | Price/discount, cancellation, refund and receipt paths passed paired-Counter UAT; exchange remains explicitly gated. |
| D25 | `design-system/25-restaurant-pos-cancel-item-sheet.png` | WP52 | Adapted | Pending/after-kitchen preview, bill impact, recipe Waste, KDS/Audit disclosure and maker-checker passed UAT. |
| D26 | `design-system/26-restaurant-pos-discount-sheet.png` | WP52 | Adapted | Server-authoritative amount/percent workspace passed Desktop/iPad UAT. |
| D27 | `design-system/27-restaurant-pos-manager-approval.png` | WP52 | Adapted | Bounded action/reason summaries and different-user maker-checker opened correctly for Cancellation and Refund. |
| D28 | `design-system/28-restaurant-pos-refund-sheet.png` | WP52 | Adapted | Server quote, original-payment allocation, Sandbox boundary and non-fiscal tax state passed Desktop/iPad UAT. |
| D29 | `design-system/29-restaurant-pos-held-bills-server-backed.png` | WP51 | Implemented | Server remains the source of truth; hold creates no payment, stock, tax or KDS side effect. |
| D30 | `design-system/30-customer-qr-ordering-flow.png` | WP49/WP64 | Adapted | Session-scoped Restaurant QR works; broader Public Experience is WP64. |
| D31 | `design-system/31-restaurant-kds-pickup-flow.png` | WP49/WP52 | Adapted | KDS works; final Order Center/Pickup cohesion is WP52. |
| D32 | `design-system/32-restaurant-pos-bill-receipt-center.png` | WP52 | Adapted | Current-shift refresh/search/filter/detail, receipt, eligible/ineligible Void and Refund routing passed paired-Counter UAT. |
| D33 | `design-system/33-restaurant-pos-offline-sync-recovery.png` | WP53 | Implemented; conditional UAT | Real encrypted outbox drives list-detail UX; paired empty-state/tablet/rollback passed, stateful network paths remain WP54. |
| D34 | `design-system/34-restaurant-pos-counter-readiness-check.png` | WP54 | Implemented; delivery gate closed | Automatic evidence and physical evidence are separated; 15 physical checks remain open and Browser capability is not a physical pass. |

## Image acceptance registry — Retail POS R01–R10 (10)

| # | Approved image | WP | Current state | Contract/readiness note |
|---:|---|---|---|---|
| R01 | `retail-pos/01-retail-pos-foundation-flow-board.png` | WP55 | Authenticated UAT passed | Retail shell is selected by signed context; Legacy source remains unchanged. |
| R02 | `retail-pos/02-retail-pos-scan-first-sale.png` | WP55 | Authenticated UAT passed | Brand-scoped scan-first Catalog, isolated cache and online-only checkout fail closed. |
| R03 | `retail-pos/03-retail-pos-product-exception-states.png` | WP56 | Software Gate passed; physical HOLD | Signed Server lookup returns persistent unknown/ambiguous/Variant/stock/price states and fails closed. |
| R04 | `retail-pos/04-retail-pos-cart-customer-discount.png` | WP56 | Software Gate passed; physical HOLD | Server quote and masked customer data are active; Loyalty is disabled until atomic reservation exists. |
| R05 | `retail-pos/05-retail-pos-payment-receipt.png` | WP56 | Software Gate passed; physical HOLD | Cash Pilot only; non-cash/offline fail closed and hardware remains physical-UAT gated. |
| R06 | `retail-pos/06-retail-pos-hold-resume-bill-v2.png` | WP57 | Software UAT passed; physical HOLD | Server-backed Hold, version/conflict/idempotency and signed Retail context passed authenticated UAT. |
| R07 | `retail-pos/07-retail-pos-return-exchange-void.png` | WP57 | Software UAT passed; physical HOLD | Cash Return maker-checker and exact-once side effects passed; Exchange/provider/tax retry remain fail-closed. |
| R08 | `retail-pos/08-retail-pos-shift-operations.png` | WP57 | Software UAT passed; physical HOLD | Retail shift authority stayed isolated to Retail and outside the shared journal; Production cutover remains unauthorized. |
| R09 | `retail-pos/09-retail-pos-offline-sync-recovery.png` | WP58 | Implemented; software UAT passed | Context-isolated recovery states are active; Retail offline sale remains disabled. |
| R10 | `retail-pos/10-retail-pos-counter-readiness.png` | WP58 | Implemented; physical HOLD | Business-aware readiness is active; scanner/printer/drawer require physical UAT. |

## Non-image product areas retained in the program

| Area | Design authority | WP | Current state / boundary |
|---|---|---|---|
| Platform Console | `cto-non-hotel/01-PLATFORM-CONSOLE-CTO-SPEC.md` | WP59 | In progress; server-authoritative RBAC, Team invitation, session/MFA visibility, access review and last-owner protection implemented locally. |
| Company Admin | `cto-non-hotel/02-COMPANY-ADMIN-CTO-SPEC.md` | WP60 | Planned maturity on top of WP42. |
| Shared ERP | `cto-non-hotel/03-SHARED-ERP-CTO-SPEC.md` | WP61 | Planned; real tax/provider/accountant acceptance remains gated. |
| Restaurant advanced | `cto-non-hotel/04-RESTAURANT-ADVANCED-OPERATIONS-CTO-SPEC.md` | WP49–WP54 | Active sequence; Brand-profile-specific extras remain disabled until approved. |
| Takeaway | `cto-non-hotel/05-TAKEAWAY-POS-CTO-SPEC.md` | WP62 | Engineering exists; real-data/canary/owner gates remain. |
| Central Kitchen / Supply Chain | `cto-non-hotel/06-CENTRAL-KITCHEN-SUPPLY-CHAIN-CTO-SPEC.md` | WP63 | Read-only/dark-launch; opening lot, count, QC and recall gates remain. |
| Public Customer Experience | `cto-non-hotel/07-PUBLIC-CUSTOMER-EXPERIENCE-CTO-SPEC.md` | WP64 | Catalog versus ecommerce decision remains with Owner. |
| Integration / Reporting / Governance | `cto-non-hotel/08-INTEGRATION-REPORTING-GOVERNANCE-CTO-SPEC.md` | WP65 | Planned reconciliation, incident, evidence and retention maturity. |

## Governance rules

1. Source/API/schema and the latest tracked Phase Gate outrank static images.
2. Each active WP must update this registry when a row changes state.
3. `Implemented` requires Local/UAT evidence and a closed Phase Gate; a visual match alone is insufficient.
4. Readiness and permission are independent and both fail closed.
5. No image authorizes Production, a real provider, a real tax document, Retail cutover, Takeaway/Central writes or Hotel PMS.
6. `docs/ux-ui/` remains user-owned reference material and is never staged by Engineering.
