# UAT Automatic Login Mode

Date: 2026-09-23

Status: **AUTHORIZED FOR SOLO UAT REVIEW / PRODUCTION FORBIDDEN**

## Purpose

Foodchainservice UAT may skip credential entry while the Product Owner reviews
all Desktop and Tablet pages alone. Tenant/POS/Admin routes use the configured
Company Super Admin. Platform Console routes use the configured Platform Admin.
Normal Server-side permissions and signed Company/Branch context remain active.

Device Pairing is not bypassed. Pairing proves a physical Counter, Kitchen or
Pickup device and is a separate security boundary from staff login.

## Runtime guard

Automatic login is available only when all conditions pass:

- `ENVIRONMENT=development` after the UAT Compose override;
- `SAAS_PUBLIC_BASE_URL` is HTTPS and its hostname begins with `uat-`;
- the request Host exactly matches the configured UAT hostname;
- `UAT_AUTH_BYPASS_ENABLED=true`;
- explicit Company, Tenant username and Platform username are configured;
- the configured users are active and have valid Server-side access.

The application refuses to start with this mode in Production, staging, HTTP
UAT or a non-`uat-*` public hostname. The endpoints are hidden from API docs and
return HTTP 404 whenever the guard is not satisfied.

## UAT identities and rollback

Runtime usernames and Company ID stay in the protected UAT environment file;
no password, key or token is stored in Git. QA Access Mode must be disabled
while this legacy credentialless mode is enabled.

To restore formal role/permission UAT, set `UAT_AUTH_BYPASS_ENABLED=false`, set
`QA_ACCESS_MODE_ENABLED=true`, recreate only UAT Backend/Frontend and revoke the
temporary automatic-login sessions.

## Deployment evidence

- Commit: `f556aea5a1d50da25a932d71c54ffadac2c37d15`
- Source archive SHA-256:
  `50e214b763ec037837f9ca185f38f72d46dda44c71de94c925122957827f6255`
- Backend: `restaurant-pos-backend:uat-login-f556aea`, image
  `sha256:3a166e733c98e96392ca41e88453f8b68ed663bf2cee72d25d7ca65808e7b837`
- Frontend: `restaurant-pos-frontend:uat-login-f556aea`, image
  `sha256:4507eb35827485d49346ded23b55498f8c93d338e2ec41d0a1f064f2cf90a1b1`
- Backend regression: 564 passed, 1 skipped.
- Frontend TypeScript and production PWA build: passed.
- Tenant auto-login issued `admin` with Super Admin permission and returned a
  signed Company context.
- Platform auto-login issued `qa.platform-admin` with the active UAT
  `platform_owner` role and opened Platform Dashboard.
- Wrong-host requests and both QA-key endpoints returned HTTP 404.
- Browser UAT opened `/admin`, `/pos`, `/takeaway`, `/company/governance`,
  `/integrations` and `/platform` without credential entry; browser console
  errors were zero.
- UAT Postgres, Redis, Nginx and Cloudflared identities stayed unchanged.
- All Production container identities and images stayed unchanged.
