# WP60 — Company Admin Maturity, Access Review and Company Audit

Status: IN PROGRESS — discovery and contract freeze
Environment: Local first; UAT after focused checkpoint
Production: HOLD

## Objective

Mature Company Admin identity governance without mixing Platform operators with
tenant users. Company Owner/Admin must be able to manage personal staff
accounts, roles and Company/Brand/Branch scope, review access and inspect an
auditable history through server-authoritative contracts.

## Existing baseline to preserve

- Company/Brand/Branch context and role-aware landing from WP36–WP42.
- Company People & Access UI, user list, role list and scoped role-assignment
  endpoints.
- Company activity/audit data, module readiness, Action Center and Product
  Readiness.
- Company identities remain separate from Platform operators and device
  identities.

## Planned slices

1. **Contract and isolation audit** — inventory current user, role, assignment,
   invitation, session and audit paths; close legacy bypasses and require exact
   Company scope.
2. **People lifecycle** — personal invitations, active/inactive state, last
   owner/admin protection and immediate session invalidation on access change.
3. **Role and scope governance** — least-privilege Company/Brand/Branch
   assignments, concurrency/idempotency checks and reason-required mutations.
4. **Access review and security visibility** — last login, active sessions, MFA
   policy/readiness, stale access and periodic review evidence.
5. **Company audit experience** — actor, action, target, scope, reason,
   request id and before/after filters with safe deep links.
6. **Responsive UI and states** — Organization, People & Access and Company
   Audit with Loading, Empty, Error, Offline, Stale and Permission denied on
   desktop/tablet.

## Hard gates

- Server authorization is authoritative and deny by default.
- All reads and writes are Company-scoped; cross-Company identifiers fail
  closed.
- Last Company Owner/Admin protection is transactional.
- Role/state changes revoke affected sessions immediately and emit audit
  evidence.
- MFA enforcement cannot be enabled for real tenants until recovery, owner
  policy and UAT handoff are accepted.

## Explicit holds

- No Production deployment or forced tenant MFA.
- No real email/SMS delivery, provider transaction or tax document.
- No Retail source cutover or Takeaway/Central Kitchen write activation.
- No deletion or rewrite of historical tenant audit evidence.

## First checkpoint

Produce the current-contract matrix and focused isolation/last-owner/session
tests before changing the People & Access UI. UAT deployment requires a
dedicated commit, immutable images, backup, migration rehearsal when applicable,
authenticated role journey, rollback/restore and Production identity proof.
