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
| 2 | `SAAS-PREP-PLATFORM-AUTH-02` | MFA-ready Platform sessions, logout, revocation, and recovery controls | Scope 01 | Complete |
| 3 | `SAAS-PREP-TENANT-USAGE-03` | Plan usage, conditional onboarding, last activity, and attention queue | Scope 02 | Complete |
| 4 | `SAAS-PREP-MEMBERSHIP-04` | Self-service tenant signup, verification, reset, trial, and onboarding lifecycle | Scope 03 | Complete |
| 5 | `SAAS-PREP-OPERATIONS-05` | Protected operations summary, health snapshots, alert and backup status | Scope 04 | Complete |
| 6 | `SAAS-PREP-BILLING-06` | Provider-neutral subscription lifecycle and billing decision boundary | Scope 05; provider selection remains parked | Complete |
| 7 | `SAAS-PREP-PDPA-SUPPORT-07` | Privacy lifecycle, data-subject requests, support tickets, and audited support access | Scope 06 | Complete |
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

## SAAS-PREP-PLATFORM-AUTH-02

### Problem

Platform authentication currently issues one bearer token, persists it in browser local
storage, and performs logout only in the client. There is no server-side session revocation,
MFA enrollment, recovery code, or controlled operator password recovery.

### In scope

- Add Platform-only server sessions with hashed rotating refresh credentials, CSRF binding,
  expiry, current/all-session logout, session listing, and per-session revocation.
- Bind Platform access tokens to a live server session and reject legacy, tenant, device,
  expired, revoked, or stale-generation credentials.
- Add TOTP enrollment/confirmation, MFA login, one-time recovery codes, recovery-code
  rotation, and protected MFA disable.
- Encrypt TOTP secrets at rest using the existing application secret boundary and declare
  the cryptography package as a direct dependency.
- Move Platform browser persistence from local storage to session storage and refresh
  access credentials through an HttpOnly, Secure-in-production, same-site cookie.
- Add authenticated password change and an audited CLI break-glass password-reset path.
- Add Platform security UI, focused migration/auth tests, and browser verification.
- Add matching legacy and Platform-core Alembic migrations; do not apply them to production.

### Out of scope

- Tenant staff sessions, device sessions, public signup, email delivery, SMS OTP, SSO, and
  external identity providers.
- Public forgot-password email links; those require the membership and notification scopes.
- Production secrets, production migration execution, or production deployment.

### Acceptance criteria

- Revoked/logout sessions cannot authorize Platform endpoints or refresh tokens.
- Refresh credentials are opaque, hashed at rest, rotated on every use, and CSRF-bound.
- Enabling MFA requires a valid TOTP; subsequent login requires TOTP or consumes one valid
  recovery code exactly once.
- TOTP secrets are encrypted at rest and recovery codes are stored only as hashes.
- Platform authentication state is not stored in browser local storage.
- Auth migrations upgrade/downgrade cleanly on isolated databases.
- Backend auth tests, frontend type-check/build, and Platform security browser flows pass.

### Verification

- Focused Platform auth/session/MFA unit and API tests.
- Upgrade, downgrade, and re-upgrade both affected migration paths on isolated databases.
- `npm run type-check`, `npm run build`, and Platform Playwright suite.

### Rollback

Revert only the Scope 02 commit and downgrade the Scope 02 migration before reverting the
application. Existing tenant and device authentication tables are not modified.

### Completion evidence

- Focused Platform suite: 33 tests passed, including TOTP vectors, encrypted secret
  round-trip, one-time TOTP/recovery use, refresh rotation, CSRF, and session binding.
- Isolated legacy migration: `6b7c8d9e0f12` → `p6auth0008` → `p5tenant0007` →
  `p6auth0008` passed.
- Isolated Platform-core migration: `p1platform0003` → `p6platform0010` →
  `p5platform0009` → `p6platform0010` passed.
- Isolated auth API smoke: login, refresh rotation, stale CSRF rejection, MFA enrollment,
  recovery login, logout revocation, password change, and credential-generation revocation
  passed.
- Frontend TypeScript check and production build: passed.
- Platform browser suite: 4 tests passed, including the security/MFA enrollment flow.
- Gate manifest: `/private/tmp/restaurant-saas-artifacts/saas-platform-auth-02-20260803T064239Z/manifest.txt`.
- Temporary databases remaining: `0`; local legacy and Platform migration heads unchanged.

## SAAS-PREP-TENANT-USAGE-03

### Problem

The Platform dashboard shows global resource totals but does not tell the owner which
Tenant is approaching or exceeding a plan limit, when a Tenant last used the system, or
why a Tenant needs attention. There is also no durable aggregate snapshot for later trend
and billing decisions.

### In scope

- Compute Company-level usage for brands, branches, enabled user accounts, registered and
  paired devices, and active menu items.
- Compare usage to manual plan limits using the existing zero-as-unlimited convention.
- Compute last activity only from aggregate timestamps such as operator audit, staff login,
  device last-seen, configuration update, and menu update.
- Add deterministic attention rules for suspension, incomplete setup, plan-limit breach,
  unpaired devices, stale activity, and configured-but-planned product flags.
- Store on-demand aggregate usage snapshots in legacy and Platform-core migration paths.
- Add protected current usage/history and snapshot-capture APIs with audit evidence.
- Add dashboard attention/last-activity UI and focused backend/browser verification.

### Out of scope

- Order lines, receipts, customer names, customer contact data, employee personal data, or
  any Platform endpoint returning Tenant business records.
- Automated scheduler, metered billing, invoices, payment providers, automatic suspension,
  or changing plan limits.
- Production migration execution, production monitoring, Takeaway Phase 6, or Retail Phase 7.

### Acceptance criteria

- Each active Company has current aggregate usage, limit state, last activity, and explainable
  attention codes without exposing order/customer detail.
- A limit of zero is reported as unlimited and never produces a limit-breach alert.
- Snapshot capture is explicit, idempotent per Company/day, Platform-authorized, and audited.
- Current usage and snapshot history remain isolated by requested Company.
- Both migration paths rehearse upgrade/downgrade/re-upgrade on isolated databases.
- Backend focused tests, frontend type-check/build, and Platform browser flow pass.

### Verification

- Focused aggregate/limit/attention unit and API tests.
- Isolated migration rehearsal for legacy and Platform-core paths.
- `npm run type-check`, `npm run build`, and Platform Playwright suite.

### Rollback

Revert only the Scope 03 commit and downgrade the Scope 03 migration after exporting any
aggregate snapshots that must be retained. No Tenant operational record is changed.

### Completion evidence

- Focused Platform suite: 35 tests passed, including unlimited/limit breach and explainable
  attention rules.
- Isolated legacy migration reached `p7usage0009` and passed downgrade to `p6auth0008`
  followed by re-upgrade.
- Isolated Platform-core migration reached `p7platform0011` and passed downgrade to
  `p6platform0010` followed by re-upgrade.
- Isolated usage API smoke passed aggregate-only response, PII leak check, daily upsert
  idempotency, snapshot audit, and Company isolation gates.
- Frontend TypeScript check, production build, and 4 Platform browser tests passed.
- Gate manifest: `/private/tmp/restaurant-saas-artifacts/saas-tenant-usage-03-20260803T065817Z/manifest.txt`.
- Temporary databases remaining: `0`; local legacy and Platform migration heads unchanged.

## SAAS-PREP-MEMBERSHIP-04

### Problem

Staff accounts and CRM loyalty records exist, but a prospective Restaurant SaaS owner
cannot create a Tenant, verify ownership of an email address, recover a forgotten password,
or enter a controlled trial without a Platform operator creating the account manually.
The current Tenant SMTP settings are not suitable for pre-Tenant account messages.

### In scope

- Add public self-service signup for one Restaurant pilot Tenant and one Company Owner.
- Require terms/privacy acceptance and normalized unique owner email for public signup.
- Store a provider-neutral Tenant membership lifecycle with pending verification, active
  trial, expired trial, active, suspended, and cancelled states.
- Use single-use, time-limited, hashed email-verification and password-reset credentials;
  never persist or log a raw credential.
- Add resend-verification and non-enumerating forgot-password endpoints with basic
  application-level request throttling that remains safe when Redis is unavailable.
- Add system-level SMTP delivery configuration for account messages. Production must use
  configured SMTP and HTTPS public links; development/test may use an explicit console
  transport that does not output raw credentials.
- Start a 14-day trial only after email verification, block login/refresh before
  verification and after trial expiry, and revoke existing refresh sessions after a
  password reset.
- Expose the current lifecycle to the authenticated Tenant owner and a protected summary
  to the Platform owner without exposing raw credentials.
- Add signup, verification, forgot/reset, and completion pages to the web application.
- Add matching legacy and Platform-core Alembic migrations; rehearse only on isolated
  databases and do not apply them to production.

### Out of scope

- Subscription charging, cards, bank accounts, QR payment, invoices, tax receipts, coupons,
  payment-provider webhooks, or automatic paid-plan activation.
- SMS/LINE OTP, social login, SSO, native-app signup, custom domains, or marketing journeys.
- Staff invitation changes, CRM loyalty membership changes, production deployment,
  hardware UAT, Takeaway Phase 6, and Retail Phase 7.

### Acceptance criteria

- A new owner can sign up, but cannot log in until a valid verification credential is used.
- Verification credentials expire, are stored only as hashes, and can be consumed once.
- Verification begins exactly one trial window and returns the Company ID required by the
  existing Tenant login boundary.
- Forgot-password responses do not reveal whether an email exists; reset credentials
  expire, are single-use, and a successful reset revokes every prior Tenant refresh token.
- Pending, expired, suspended, and cancelled memberships cannot create or refresh sessions;
  legacy Companies without a membership record remain compatible.
- Production configuration rejects console delivery, incomplete SMTP settings, or a
  non-HTTPS public URL.
- Both migration paths rehearse upgrade/downgrade/re-upgrade on isolated databases.
- Focused backend tests, API smoke, frontend type-check/build, and browser flows pass.

### Verification

- Focused membership schema, credential, lifecycle, access-policy, and configuration tests.
- Isolated public membership API smoke with an in-process mail capture that proves raw
  credentials are absent from API responses and database credential columns.
- Upgrade, downgrade, and re-upgrade both affected migration paths on isolated databases.
- `npm run type-check`, `npm run build`, and public membership Playwright flow.

### Rollback

Disable public membership routes, revert only the Scope 04 commit, then downgrade the Scope
04 migration after confirming no pending signup or reset action must be retained. Existing
Platform-created Companies and legacy Tenant login behavior remain compatible.

### Completion evidence

- Focused membership suite: 5 tests passed; focused Platform regression suite: 35 tests
  passed.
- Isolated legacy migration reached `p8member0010` and passed downgrade to `p7usage0009`
  followed by re-upgrade.
- Isolated Platform-core migration reached `p8platform0012` and passed downgrade to
  `p7platform0011` followed by re-upgrade.
- Isolated membership API smoke passed pending/expired access blocks, verification and
  reset credential single-use, hash-only persistence, forgot-password non-enumeration,
  refresh revocation, new-password login, and protected Platform lifecycle visibility.
- Account links carry credentials in the URL fragment so reverse-proxy request paths do
  not receive them; console delivery logs only a one-way recipient reference.
- Frontend TypeScript check, production build, and 5 Platform/public-account browser tests
  passed.
- Gate manifest: `/private/tmp/restaurant-saas-artifacts/saas-membership-04-20260803T072035Z/manifest.txt`.
- Temporary databases remaining: `0`; local legacy and Platform migration heads unchanged.

## SAAS-PREP-OPERATIONS-05

### Problem

Readiness checks, three-boundary backup/restore tooling, and a resilience monitor already
exist, but the public readiness response exposes internal database routing and projector
details. Platform Owner has no protected summary or durable, sanitized history of runtime,
backup, restore-drill, disk, and alert-delivery status.

### In scope

- Reduce public liveness/readiness responses to status and version without database names,
  routing mode, projector counters, paths, exception classes, or internal error details.
- Reuse the existing dependency checks behind a protected Platform operations service.
- Store sanitized operational snapshots containing component state, backup freshness,
  restore-drill state, disk threshold state, alert codes, and evidence checksum only.
- Add protected Platform summary, history, on-demand capture, and sanitized evidence-import
  endpoints with operator audit records.
- Add a scheduler-ready CLI that can capture runtime state or import a resilience evidence
  JSON file without placing bearer credentials in cron arguments.
- Extend the existing resilience evidence contract with optional restore-drill state while
  excluding backup paths and raw error text from the database/API.
- Add a Platform Operations page showing current dependency state, latest backup/restore,
  alert delivery, history, loading, empty, and failure states.
- Add matching legacy and Platform-core migrations and an isolated gate that exercises a
  real local backup/restore drill; do not apply it to production.

### Out of scope

- Installing Prometheus, Grafana, Sentry, cloud monitoring, paging vendors, log aggregation,
  or a production scheduler/cron job.
- Exposing logs, environment variables, connection strings, database names, filesystem
  paths, stack traces, Tenant records, or backup contents through Platform APIs.
- Performing a production restore, production deployment, hardware UAT, Takeaway Phase 6,
  or Retail Phase 7.

### Acceptance criteria

- Anonymous health responses reveal no internal topology or sensitive failure detail.
- Only an active Platform session can view/capture/import operational evidence.
- Stored/API snapshots use a fixed allow-list and never retain an evidence path, raw alert
  body, exception text, secret, or Tenant business data.
- Duplicate evidence checksum import is idempotent.
- Runtime capture reports each required dependency as `ok` or `error` and stores no
  exception details.
- Backup freshness, restore-drill result, and alert-delivery state are explicit, including
  `unknown` when evidence is absent.
- Both migration paths rehearse upgrade/downgrade/re-upgrade on isolated databases.
- Focused backend tests, API/backup/restore smoke, frontend type-check/build, and browser
  flows pass.

### Verification

- Health sanitization, snapshot allow-list, evidence parsing/idempotency, and Platform
  authorization tests.
- Isolated migration rehearsal and protected API smoke.
- Existing three-boundary local backup plus isolated restore drill, with checksum evidence.
- `npm run type-check`, `npm run build`, and Platform Operations Playwright flow.

### Rollback

Revert only the Scope 05 commit and downgrade its migration after exporting any operational
history that must be retained. Existing backup/restore and resilience scripts continue to
operate independently; no production restore or scheduler change is part of this Scope.

### Completion evidence

- Focused Platform suite: 38 tests passed, including public health sanitization and
  evidence allow-list parsing.
- Isolated legacy migration reached `p9ops0011` and passed downgrade to `p8member0010`
  followed by re-upgrade.
- Isolated Platform-core migration reached `p9platform0013` and passed downgrade to
  `p8platform0012` followed by re-upgrade.
- Protected API smoke passed anonymous rejection, live runtime capture, extra-field
  rejection, checksum-idempotent import, summary/history, audit, and sensitive-marker gates.
- Three isolated database-boundary dumps passed checksums; the restore drill reconstructed
  all three boundaries, reproduced the Tenant checksum, and completed in 5 seconds.
- Scheduler CLI imported resilience/restore evidence after reducing it to approved states,
  counters, and alert codes; no path or raw alert text entered the table/API.
- Frontend TypeScript check, production build, and 6 Platform/public-account browser tests
  passed, including Operations loading, summary, and capture flow.
- Gate manifest: `/private/tmp/restaurant-saas-artifacts/saas-operations-05-20260803T073547Z/manifest.txt`.
- Temporary databases remaining: `0`; local legacy, Platform, and Restaurant migration
  heads unchanged.

## SAAS-PREP-BILLING-06

### Problem

Tenant profiles contain a manual `plan_code`, and verified SaaS owners have a trial window,
but there is no durable plan catalog, subscription period, SaaS invoice lifecycle, or
normalized event contract. Selecting or integrating a payment provider now would invent a
commercial decision that the owner has not supplied.

### In scope

- Add a provider-neutral plan catalog whose price may remain explicitly undecided (`null`).
- Add one SaaS subscription per Company with incomplete, trialing, active, past-due,
  paused, and cancelled lifecycle states and period/cancellation timestamps.
- Backfill existing self-service memberships to a starter subscription and keep new
  signup/email-verification trial timestamps synchronized with that subscription.
- Add SaaS invoice records using integer satang amounts, THB currency by default, and
  draft/open/paid/void/uncollectible states; do not reuse Restaurant sale/payment records.
- Add a normalized billing event envelope that stores only an idempotency key, fixed event
  type, normalized references/amounts, and payload checksum—never a raw provider payload.
- Add protected Platform plan, Company billing summary, manual subscription, invoice, and
  normalized-event APIs with reasoned audit logs.
- Add an authenticated owner billing summary that is read-only and explicitly reports that
  payment collection is unavailable while the provider is unconfigured.
- Add Platform billing UI and Tenant billing status UI without card/bank/QR forms.
- Add configuration guards that keep live charging disabled while provider selection is
  unconfigured.
- Add matching legacy and Platform-core migrations and isolated verification.

### Out of scope

- Selecting Stripe, Omise, 2C2P, GB Prime Pay, a bank, PromptPay collection, or any other
  provider; provider SDKs, secrets, webhooks, checkout, cards, mandates, refunds, payouts,
  coupons, tax invoices, or revenue recognition.
- Automatic charging, automatic suspension for non-payment, collections emails, dunning,
  exchange rates, or production price decisions.
- Restaurant POS payments, production deployment, hardware UAT, Takeaway Phase 6, and
  Retail Phase 7.

### Acceptance criteria

- The default provider state is `unconfigured` and live charging is false in API/UI.
- Production configuration cannot enable live charging without a non-empty provider
  decision, and this Scope contains no provider adapter or secret field.
- Existing/new verified memberships have one idempotently created starter subscription;
  membership verification synchronizes one trial period without creating duplicates.
- Monetary values are non-negative integer satang with one invoice currency and arithmetic
  constraints (`subtotal + tax = total`, `paid <= total`).
- Normalized event keys are unique; replay returns the original result and cannot apply a
  transition twice. Raw payloads and credentials are rejected/not persisted.
- Only Platform Owner may mutate plans, subscriptions, invoices, or events; Tenant owner
  sees only its own read-only billing summary.
- Both migration paths rehearse upgrade/downgrade/re-upgrade on isolated databases.
- Focused backend tests, API smoke, frontend type-check/build, and browser flows pass.

### Verification

- Configuration, plan/amount validation, subscription transition, invoice arithmetic,
  event allow-list/idempotency, authorization, and Tenant-isolation tests.
- Isolated migrations plus Platform/Tenant billing API smoke with raw-payload rejection.
- `npm run type-check`, `npm run build`, and Platform/Tenant billing browser flows.

### Rollback

Keep live charging disabled, export any manual billing records that must be retained, revert
only the Scope 06 commit, and downgrade its migration. Membership trial access remains
governed by Scope 04 and Restaurant payment records are unaffected.

### Completion evidence

- Focused billing suite: 6 tests passed; focused Platform regression suite: 38 tests passed.
- Isolated legacy migration reached `p10bill0012` and passed downgrade to `p9ops0011`
  followed by re-upgrade.
- Isolated Platform-core migration reached `p10platform0014` and passed downgrade to
  `p9platform0013` followed by re-upgrade.
- Isolated API smoke passed signup-to-trial subscription synchronization, Tenant read-only
  boundary, Platform-only mutations, integer-satang invoice arithmetic, allowed state
  transitions, normalized raw-payload rejection, checksum persistence, idempotent replay,
  conflicting-key rejection, and audit evidence.
- Provider remains `unconfigured`; configuration rejects every attempt to enable live
  charging because no provider adapter Scope has been approved.
- Frontend TypeScript check, production build, and 8 Platform/public/Tenant browser tests
  passed, including plan pricing conversion and absence of a Tenant payment action.
- Gate manifest: `/private/tmp/restaurant-saas-artifacts/saas-billing-06-20260803T075734Z/manifest.txt`.
- Temporary databases remaining: `0`; local legacy and Platform migration heads unchanged.

## SAAS-PREP-PDPA-SUPPORT-07

### Problem

The SaaS account owner has no controlled way to submit or track an account-level privacy
request or support case. Platform operators have no tenant-approved, expiring access grant,
so informal troubleshooting could become broad or unaudited access. Existing Tenant export
and audit tools are Platform-only and are not a complete data-subject workflow.

### In scope

- Add authenticated account-owner privacy requests for access, export, correction,
  deletion, restriction, objection, and consent withdrawal, isolated to the owner's Company.
- Treat the configured response target as an internal operating target, not a legal opinion
  or a guarantee of statutory compliance.
- Let Platform Owner verify, review, fulfill, reject, or cancel requests with status history,
  response summary, reason, and audit evidence; no request directly deletes data.
- Add explicit retain/delete/anonymize retention decisions linked to a request, including
  data category, rationale, optional retain-until date, and proposed/approved/rejected
  lifecycle. Execution remains outside this Scope.
- Add Tenant support tickets and conversation messages with category, priority, status,
  requester identity, and Company isolation.
- Let a Platform operator request an allow-listed support grant for one ticket and Company;
  only that Tenant owner can approve or deny it.
- Limit approved grants to named aggregate scopes, cap their lifetime, allow either side to
  revoke them, and audit request, decision, context view, expiry, and revocation.
- Expose only an allow-listed support context (account state, SaaS controls, onboarding,
  aggregate usage/billing state) and never issue an impersonation token or return orders,
  customers, staff records, credentials, or secrets.
- Add Tenant Privacy & Support UI and Platform Support UI.
- Add matching legacy and Platform-core migrations and isolated verification.

### Out of scope

- Legal advice, a compliance certification, automatic interpretation of PDPA obligations,
  or hard-coded statutory exceptions/retention periods.
- Automatic deletion/anonymization, database row mutation based on a request, legal hold
  execution, consent/banner management, cookie scanning, or customer-facing DSAR forms for
  a Tenant's own diners or loyalty customers.
- Silent impersonation, password/session takeover, unrestricted SQL, order/customer/staff
  detail access, file attachments, screen control, remote shell, or production access.
- External help-desk providers, email/SMS notifications, production deployment, hardware
  UAT, Takeaway Phase 6, and Retail Phase 7.

### Acceptance criteria

- A Tenant owner can create/list only its Company's privacy requests and support tickets;
  another Tenant cannot view, message, decide, or approve them.
- Privacy and retention mutations require a reason and create audit evidence. A retention
  decision records intent only and performs no destructive data operation.
- A Platform operator cannot view support context until the matching Tenant owner approves
  a named-scope grant; pending, denied, revoked, or expired grants are rejected.
- Grant lifetime is capped, context fields are allow-listed, and every successful context
  view is audited without returning raw business records or credentials.
- No route creates an impersonated Tenant token or changes a Tenant user's password/session.
- Both migration paths rehearse upgrade/downgrade/re-upgrade on isolated databases.
- Focused backend tests, API smoke, frontend type-check/build, and browser flows pass.

### Verification

- Schema/state/expiry/allow-list tests plus Company-isolation and authorization API smoke.
- Database evidence proving grant decisions/views and privacy/retention changes are audited.
- Sensitive-field scan of support-context/API artifacts and route contract.
- Isolated migrations, `npm run type-check`, `npm run build`, and Platform/Tenant browser flows.

### Rollback

Revoke all active support grants, export request/ticket metadata that must be retained,
revert only the Scope 07 commit, and downgrade its migration. No automatic deletion or
Tenant session mutation must be unwound because neither is authorized in this Scope.

### Completion evidence

- Focused Privacy/Support suite: 4 tests passed; focused Platform regression suite: 38
  tests passed.
- Isolated legacy migration reached `p11privacy0013` and passed downgrade to
  `p10bill0012` followed by re-upgrade.
- Isolated Platform-core migration reached `p11platform0015` and passed downgrade to
  `p10platform0014` followed by re-upgrade.
- API smoke used two verified SaaS Tenants and two Platform operators. Cross-Tenant privacy,
  ticket, message, and grant decisions were rejected; a grant was bound to its requesting
  operator.
- Pending, wrong-Tenant, wrong-operator, revoked, and expired access could not view support
  context. An approved grant returned exactly its named account/control/billing scopes and
  every successful view created audit evidence.
- Support-context sensitive-marker scan passed; the grant schema has no password, token,
  secret, or impersonation field, and the Platform exposes no impersonation route.
- Retention proposal/approval and privacy fulfillment were audited while Company/User row
  counts remained unchanged, proving the workflow performed no destructive execution.
- Frontend TypeScript check, production build, and 10 Platform/public/Tenant browser tests
  passed, including Tenant grant approval and Platform access-request flows.
- Gate manifest: `/private/tmp/restaurant-saas-artifacts/saas-privacy-support-07-20260803T081908Z/manifest.txt`.
- Temporary databases remaining: `0`; local legacy and Platform migration heads unchanged.

## Later-scope boundaries

### SAAS-PREP-BETA-GATE-08

Evidence only: migrations, authorization, tenant isolation, dependency review, load,
browser flows, backup/restore, and operator handoff. Passing this gate still does not
activate production without Restaurant physical UAT and owner sign-off.

## Change control

Any request that adds a new provider, business type, production environment, custom domain,
native application, analytics product, marketing site, AI feature, or operational database
must be recorded as a separate future Scope. It must not be absorbed into this work queue.
