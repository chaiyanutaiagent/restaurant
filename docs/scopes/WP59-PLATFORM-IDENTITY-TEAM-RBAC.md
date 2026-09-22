# WP59 — Platform Identity, Team/RBAC and Operator Governance

Status: IN PROGRESS
Environment: Local and UAT only
Production: HOLD

## Objective

Replace the Platform Console's single `is_superuser` authorization gate with
server-authoritative, deny-by-default roles and permissions while preserving the
existing bootstrap owner account.

## Included

- Canonical Platform roles: Owner, Operations, Support, Billing, Security and Auditor.
- Environment-scoped role assignments (`uat` and `production`).
- Personal operator invitation and acceptance flow; invitation credentials are
  stored only as hashes and expire.
- Operator MFA, session, last-login, credential-version, stale-access and access-review visibility.
- Assign/revoke role, deactivate/reactivate operator, revoke sessions and certify access.
- Immediate session revocation when an operator's effective access changes.
- Last active Platform Owner protection for role revoke and operator deactivation.
- Audit evidence with actor, role, reason, before/after, environment and request id.
- Permission-aware Platform navigation, Team page, deep links and explicit
  loading/empty/error/offline/stale/permission-denied states.
- Desktop and tablet responsive implementation.

## Explicit holds

- No Production deployment, flag enablement or cutover.
- No Takeaway/Central Kitchen transaction enablement.
- No Retail data-source change.
- No real provider charging, refund or tax-document action.
- Physical-device UAT remains a separate gate.

## Gate

WP59 may be checkpointed after focused backend/frontend tests and a Local visual
review. Full repository validation and migration rehearsal are required at the
Batch B gate.
