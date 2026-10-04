# WP60 Contract Matrix — Company Admin and Tenant Access Governance

Date: 2026-09-22
Environment: Local checkpoint
Production: unchanged / NO-GO

| Surface | Read authority | Mutation authority | Tenant boundary | Session/Audit behavior |
|---|---|---|---|---|
| People lifecycle | `system.user.view` | `system.user.edit/delete` | exact signed `company_id`; non-company scope cannot enumerate another branch | account state uses expected credential generation, reason and request id; access change revokes sessions |
| Role/scope | `system.role.view` | `system.role.edit`, `system.user.edit` | Company-scope administration only; target user, role, brand and branch revalidated on Server | assignment/role changes invalidate every affected user and emit audit evidence |
| Access review | `system.user.view` | `system.user.edit` | Company scope required; cross-company user/assignment returns not found | retain/reduce/revoke/investigate outcomes; reduce/revoke protected by last-owner policy and idempotent request id |
| Tenant sessions | `system.user.view` | `system.user.edit` | user and session must belong to signed Company | one/all revoke supported; all-session revoke increments credential generation |
| Company Audit | Company/report view permissions | read-only | Company filter is mandatory; branch-scoped users are pinned to signed branch | actor/action/resource/request/date filters, secret redaction and safe deep links |
| Tenant MFA | `system.user.view` | none in WP60 | Company security posture only | explicit `HOLD`; enforcement false; recovery decision required |

## Server-authoritative invariants

1. UI state never grants access; signed server context and effective permissions
   are evaluated on every request.
2. User sessions are bound to a revocable server session id and user credential
   generation. Role, scope, password and account-state changes fail old tokens.
3. State-changing review/session requests require reason, request id and the
   expected credential generation. A repeated request id returns the prior
   outcome rather than applying the mutation twice.
4. Last Company Owner protection locks the Company row before counting active
   owners.
5. No WP60 endpoint enables live payments, refunds, tax documents, Retail
   source cutover or Takeaway/Central Kitchen transactions.
