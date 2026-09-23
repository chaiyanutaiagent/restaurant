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
