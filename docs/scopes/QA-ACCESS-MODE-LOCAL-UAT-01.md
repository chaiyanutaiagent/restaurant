# QA Access Mode — Local/UAT Safety Contract

Date: 2026-09-22
Status: UAT access-readiness gate passed; full persona journey QA in progress
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

## UAT activation evidence — 2026-09-22

- UAT backend release: `747929b`; frontend release: `03639b4`.
- Runtime key exists only in protected Local/UAT files with mode `600`; its
  value is excluded from source, logs, evidence and chat.
- Pre-migration backup:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/wp60-before-20260922T123038Z`
  contains Legacy, Platform, Restaurant, Retail, Takeaway, Redis and uploads
  artifacts with SHA-256 evidence.
- Legacy migration reached `wp60tenant0025`; Platform migration reached
  `p15platform0019`.
- Explicit primary QA scope is Restaurant Brand
  `foodchainservice-restaurant-uat`, Branch `BKK-01`; ambiguous multi-Branch
  selection fails closed.
- Tenant persona discovery returned all `8` configured roles and Platform
  discovery returned all `3` configured roles.
- Short-lived session issuance passed for all `11` personas. Requests without
  the runtime key and the legacy credentialless auto-login both returned 404.
- Public readiness passed and Production container identities remained
  unchanged.

Full Company/Brand/Branch journeys, state coverage and restore rehearsal remain
assigned to the dedicated QA task. Disable the flag and revoke/delete QA
identities and key material after the full-system QA sign-off.
