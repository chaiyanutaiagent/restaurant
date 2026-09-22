# WP65 — Integration, Reporting, Reconciliation and Release Governance

Date: 2026-09-23
Environment: Local and UAT only
Production: unchanged and not authorized

## Objective

Close Batch D with Server-authoritative integration controls and a Company-facing
governance workspace that reports real evidence without inventing missing
contracts. WP65 does not activate a provider, fiscal document, Retail source
cutover, Takeaway/Central Kitchen transaction or Production flag.

## Delivered contract

### API keys

- Plaintext is returned once; only a hash and prefix are retained.
- Purpose, owner/contact and explicit expiry are mandatory.
- Empty or wildcard scopes fail closed.
- Authentication accepts `X-API-Key` only; query-string credentials are rejected.
- Rotate and revoke are Server-side lifecycle actions with audit evidence.

### Webhooks

- Secrets are encrypted at rest and never returned by read endpoints.
- Secret rotation is explicit and audited.
- Incoming requests require a timestamped HMAC signature and a bounded replay
  window.
- Company/source routing is Server-owned; duplicate incoming source names are
  rejected.
- Delivery retries use bounded exponential backoff, exact delivery retry and a
  terminal dead-letter state. Provider response bodies are not retained.
- A migration helper converts safe legacy secrets and deactivates unsafe short
  secrets without printing either value.

### External orders

- The Server maps active Company SKUs, quantity and price.
- Client totals are advisory only and are compared with the calculated total.
- Unknown SKU, invalid quantity, payment-state or price mismatch enters
  `needs_review`; it cannot auto-fulfil.
- Accept/reject review and fulfilment are separate audited actions.
- Fulfilment requires accepted state, an open branch shift and the Server-priced
  item set.

### Company governance workspace

- New route: `/company/governance`.
- Shows integration, shared reporting, outbox, tax reconciliation, physical-UAT,
  audit and release evidence from Server-owned data.
- Loading, Empty, Error, Offline, Stale and Permission denied remain explicit.
- Incident Management and Retention/Legal Hold are marked `planned` because no
  safe tenant contract exists yet; no placeholder mutation is exposed.
- Production is always returned as `HOLD` from this WP contract.

## Full-system coverage matrix

| Domain | WP65 state | Release boundary |
|---|---|---|
| Platform Console | Available | Existing operator governance; real-operator acceptance remains HOLD |
| Company Admin | Available | Company context/access/audit; tenant MFA recovery remains HOLD |
| Shared ERP | Read-only evidence | Real tax/provider/accountant acceptance remains HOLD |
| Restaurant POS | Available | Software UAT exists; physical acceptance remains HOLD |
| Retail POS | HOLD | Cash Pilot only; Legacy data source unchanged |
| Takeaway POS | Dark Launch | Transaction writes remain disabled |
| Central Kitchen | Read-only | Stock/QC/recall writes remain disabled |
| Distribution | Read-only | Transfer/dispatch writes remain disabled |
| Public Customer Experience | Catalog/Locator | Ecommerce/payment/member expansion remains disabled |
| Integration and Reporting | Governed read/write controls | Provider and Production activation remain HOLD |

Hotel PMS is excluded from WP65.

## Data and migration boundaries

Migration `wp65govern0026` extends the Legacy/Shared ERP boundary only. The final
Local heads verified for the release candidate are:

- Legacy/Shared ERP: `wp65govern0026`
- Platform Core: `p15platform0019`
- Restaurant: `p6restaurant0007`
- Retail: `p13retail0007`
- Takeaway: `p6takeaway0008`

Upgrade, downgrade to `wp60tenant0025`, re-upgrade and all four dedicated
boundary upgrades passed on Local. No cross-database foreign key, join or
transaction was added.

## Security acceptance

- Tenant identity comes from the authenticated Server context, never the
  external payload.
- Query-string API keys, wildcard scopes, missing owners and missing expiry fail
  closed.
- Plaintext legacy webhook secrets fail closed until migrated.
- Invalid, expired or replayed webhook signatures are rejected.
- External price/total mismatch is quarantined.
- Retry count is bounded and dead-letter is reconstructable.
- Secret values and provider response bodies are absent from audit evidence;
  sensitive query parameter values are redacted from Backend access logs even
  when a caller submits a credential through a rejected URL.

## QA access cleanup

`app.cli.cleanup_qa_access` is intentionally available but not executed. It is
restricted to HTTPS `uat-*` development environments, an exact immutable release
and Company, and explicit final-signoff flags. Pre-existing Company Admin persona
`admin` is not a cleanup target. Cleanup remains blocked until Product Owner
final acceptance.

## Fixed HOLDs

- Production deployment and Production flags.
- Physical printer, drawer, PromptPay, tablet camera/touch and network-interrupt
  acceptance.
- Real payment/refund/tax providers and fiscal documents.
- Retail source cutover and Retail offline sale.
- Takeaway, Central Kitchen and Distribution transaction activation.
- Chambo real-data dry run or mutation.
- Incident and retention/legal-hold mutation contracts.
