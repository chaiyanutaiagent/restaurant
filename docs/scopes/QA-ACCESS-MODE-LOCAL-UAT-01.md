# QA Access Mode — Local/UAT Safety Contract

Date: 2026-09-22
Status: Local engineering gate passed; UAT enablement pending authenticated deployment channel
Production: permanently fail-closed

## Purpose

QA Access Mode removes only the need to type a persona username, password or
MFA code during the full-system QA cycle. It issues a normal, short-lived,
revocable server session for an explicitly configured existing test identity.
All tenant, Company, Brand, Branch, Station, role, permission, readiness,
approval, server-authority, idempotency and audit rules remain active.

## Safety controls

- Startup validation permits the mode only when `ENVIRONMENT=development` and
  the public host is localhost or HTTPS `uat-*`. Production/staging cannot
  start with the mode enabled.
- A runtime-only access key of at least 32 characters is mandatory. The key is
  never committed, returned by an API, stored in browser persistence or
  included in evidence.
- The configured host and key must both match. Invalid requests return 404 and
  do not reveal whether a persona exists.
- Tenant and Platform persona maps are explicit runtime configuration; the
  Server loads the existing active identity and calculates its current roles.
- QA sessions expire in 5–60 minutes, are recorded in Audit, support revocation
  and are rejected immediately when the kill switch is disabled.
- QA tokens carry a visible persona marker. The UI displays a persistent
  `QA MODE` banner with persona and Company/Branch context.
- Legacy credentialless UAT auto-login cannot be enabled at the same time.

## Explicit exclusions

- No public credentialless access.
- No authorization, approval or isolation bypass.
- No live provider, payment/refund/tax or stock-mutation exception.
- No Production flag, identity, image, database or data-source change.

## Rollback

Set `QA_ACCESS_MODE_ENABLED=false` and recreate only the UAT backend. Existing
QA access and refresh tokens then fail immediately at the authorization
dependency. Normal authentication remains available throughout.
