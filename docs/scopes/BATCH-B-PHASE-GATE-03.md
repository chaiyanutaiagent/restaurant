# Batch B Phase Gate — Platform, Company and Shared ERP

Date: 2026-09-22

Scope: WP59–WP61

Decision: **SOFTWARE UAT PASS / BATCH B CLOSED**

Production decision: **NO-GO / unchanged**

## Gate result

WP59 Platform governance, WP60 Company administration and WP61 Shared ERP now
form one tested software slice on UAT. Full regression, deny-by-default persona
checks, Desktop/Tablet visual journeys, protected QA access, immutable release
identity, backup validation, app-only rollback/restore and Production isolation
passed. Evidence is recorded in `WP61-UAT-EVIDENCE-02.md`.

No result in this gate is a physical-device, accountant, fiscal-provider,
payment-provider or Production acceptance.

## Release decision

- WP59–WP61 may remain deployed on UAT for Product Owner and designer review.
- Batch C may begin on Local/UAT with read-only/dark-launch defaults.
- WP62 may implement Takeaway operational UI, but real Takeaway transactions
  remain disabled until the separate owner/canary gate passes.
- Central Kitchen writes, Retail source cutover, live providers, real tax
  documents and Production deployment remain outside this authorization.

## Canonical UAT rollback rule

Every UAT recreate or rollback must load both compose layers:

```text
docker-compose.prod.yml + docker-compose.uat.yml
```

Omitting the UAT layer activates the environment safety validator and must be
treated as a failed health gate, never bypassed.

## Remaining external acceptance

1. Physical printer/cash drawer/tablet/PromptPay/network-loss evidence.
2. Tenant MFA and recovery-policy acceptance.
3. Accountant sign-off and fiscal/provider contracts.
4. Production change window, owner approval, monitoring and rollback owner.

