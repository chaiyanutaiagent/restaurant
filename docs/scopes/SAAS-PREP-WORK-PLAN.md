# SaaS Preparation Work Plan

## Purpose

This document controls the non-production SaaS preparation work that may continue while
Restaurant physical-device UAT is waiting for hardware. Work is executed one Scope at a
time with an explicit boundary, verification gate, rollback note, and separate commit.

This workstream does not complete Restaurant Phase 5 and does not authorize a production
deployment or the start of Takeaway Phase 6 or Retail Phase 7.

## Locked release state

```text
restaurant_physical_scope: P5-PHYSICAL-UAT-SIGNOFF-06
restaurant_physical_status: waiting_for_hardware
restaurant_completion_approved: false
production_activated: false
phase6_started: false
phase7_started: false
```

## Execution rules

1. Only one Scope may be active at a time.
2. Each Scope must declare Problem, In scope, Out of scope, Acceptance criteria,
   Verification, and Rollback before implementation begins.
3. Findings outside the active Scope go to the follow-up queue. They are not fixed in the
   active commit unless they are an approved security or regression blocker.
4. Database migrations, dependencies, external providers, production infrastructure, and
   live-data changes require an explicit entry in the active Scope.
5. Each completed Scope receives a focused test gate and a separate commit.
6. Completion of a preparation Scope does not approve hardware UAT, production activation,
   or a later business-system phase.
7. Provider-specific billing work stops at the provider decision boundary unless the owner
   supplies a provider and commercial policy.

## Work queue

| Order | Scope | Deliverable | Dependency | Status |
| --- | --- | --- | --- | --- |
| 1 | `SAAS-PREP-DASHBOARD-01` | Correct and verify the existing Platform Owner dashboard | Existing `d788d7d` baseline | Complete |
| 2 | `SAAS-PREP-PLATFORM-AUTH-02` | MFA-ready Platform sessions, logout, revocation, and recovery controls | Scope 01 | Active |
| 3 | `SAAS-PREP-TENANT-USAGE-03` | Plan usage, conditional onboarding, last activity, and attention queue | Scope 02 | Pending |
| 4 | `SAAS-PREP-MEMBERSHIP-04` | Self-service tenant signup, verification, reset, trial, and onboarding lifecycle | Scope 03 | Pending |
| 5 | `SAAS-PREP-OPERATIONS-05` | Protected operations summary, health snapshots, alert and backup status | Scope 04 | Pending |
| 6 | `SAAS-PREP-BILLING-06` | Provider-neutral subscription lifecycle and billing decision boundary | Scope 05 and provider decision | Pending |
| 7 | `SAAS-PREP-PDPA-SUPPORT-07` | Privacy lifecycle, data-subject requests, support tickets, and audited support access | Scope 06 | Pending |
| 8 | `SAAS-PREP-BETA-GATE-08` | Migration, authorization, security, load, browser, and recovery evidence | Scopes 01-07 | Pending |
| 9 | `P5-PHYSICAL-UAT-SIGNOFF-06` | Real counter, kitchen, pickup, camera, printer, and network UAT | Hardware received | Parked |
| 10 | Public launch decision | Owner-controlled go/no-go using both SaaS and Restaurant evidence | All gates and sign-offs | Blocked |

## SAAS-PREP-DASHBOARD-01

### Problem

The current dashboard provides tenant, onboarding, plan, feature, resource, and audit
summaries, but some labels imply usage rather than enabled accounts, unreleased business
systems look available, onboarding uses a fixed seven-step rule, and the Platform console
does not yet have browser-level coverage.

### In scope

- Preserve the existing Platform dashboard API and layout baseline.
- Use accurate labels for enabled accounts and paired devices.
- Represent Restaurant, Takeaway, and Retail availability explicitly instead of implying
  that all configured feature keys are released products.
- Make onboarding readiness conditional on the enabled product and operating mode where
  the current data can support the decision safely.
- Cover loading, empty, error, and authorization behavior.
- Add focused backend and browser-level Platform dashboard verification.

### Out of scope

- Platform MFA, session persistence changes, and password recovery.
- Self-service tenant signup.
- Subscription billing or revenue metrics.
- Centralized monitoring infrastructure.
- Support tickets or tenant impersonation.
- Production deployment, live migration, hardware UAT, Takeaway Phase 6, and Retail Phase 7.

### Acceptance criteria

- Dashboard labels match the data being counted.
- Unreleased products are visibly `planned` and cannot be mistaken for available SaaS modules.
- Readiness does not require an inapplicable payment or device step.
- Tenant and device credentials cannot access Platform endpoints.
- Backend focused tests, frontend type-check/build, and Platform browser flow pass.
- No database migration is added by this Scope.

### Verification

- `python -m unittest` focused Platform suite in the project backend environment.
- `npm run type-check` and `npm run build` in `frontend/`.
- Platform login/dashboard/company/audit browser flow with loading, error, and empty cases.

### Rollback

Revert only the Scope 01 commit. The pre-existing tenant lifecycle, company management,
audit, and export APIs remain the baseline.

### Completion evidence

- Backend focused Platform suite: 15 tests passed.
- Frontend TypeScript check and production build: passed.
- Platform browser suite: 3 tests passed covering login, dashboard, company, audit,
  loading, error recovery, empty data, missing credentials, and rejected credentials.
- Database migration: none.

## Later-scope boundaries

### SAAS-PREP-PLATFORM-AUTH-02

Platform-only authentication hardening. It may add Platform session and recovery records,
but must not change tenant staff authentication or create public signup.

### SAAS-PREP-TENANT-USAGE-03

Usage snapshots and attention rules. It must use aggregate operational data and must not
expose order details or customer personal data in Platform overview responses.

### SAAS-PREP-MEMBERSHIP-04

Public tenant-account lifecycle without subscription charging. Trial and verification
states are allowed; provider-specific payment collection is not.

### SAAS-PREP-OPERATIONS-05

Protected operational summaries and scheduled evidence. Public health endpoints must not
expose internal database routing or sensitive error details.

### SAAS-PREP-BILLING-06

Provider-neutral subscription state, plans, invoices, and idempotent provider-event
contracts. Live payment-provider integration requires a recorded provider decision.

### SAAS-PREP-PDPA-SUPPORT-07

Data-subject request tracking, retention decisions, support cases, and time-limited audited
support access. It does not authorize silent tenant impersonation or unrestricted data reads.

### SAAS-PREP-BETA-GATE-08

Evidence only: migrations, authorization, tenant isolation, dependency review, load,
browser flows, backup/restore, and operator handoff. Passing this gate still does not
activate production without Restaurant physical UAT and owner sign-off.

## Change control

Any request that adds a new provider, business type, production environment, custom domain,
native application, analytics product, marketing site, AI feature, or operational database
must be recorded as a separate future Scope. It must not be absorbed into this work queue.
