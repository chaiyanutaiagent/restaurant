# Temporary UAT Superadmin Across Login Surfaces

Date: 2026-09-29

Status: **AUTHORIZED FOR ACTIVE UAT / PRODUCTION FORBIDDEN**

## Purpose

During the current hands-on test cycle, the named `superadmin` identity may use
the same password on Platform, Restaurant, Retail and Takeaway Store login
surfaces. The tenant identity is scoped to one configured Company. Takeaway
Store sessions are reduced to the Store permission allowlist and remain bound
to the selected Branch, station and physical device; a `*` permission is never
placed in the Store token.

## Runtime guard

The temporary Store exception is active only when all conditions pass:

- `UAT_SUPERADMIN_ALL_LOGINS_ENABLED=true`;
- `ENVIRONMENT=development` after the UAT Compose override;
- `SAAS_PUBLIC_BASE_URL` uses HTTPS on an exact `uat-*` hostname;
- the authenticated identity is an active superuser;
- Company ID and username exactly match the protected UAT configuration.

The application refuses to start when the switch is enabled outside these UAT
conditions. A dedicated audit action records temporary superadmin sessions.
The password and its hash are never stored in Git or deployment documentation.

## Rollback

After the shared test cycle, set `UAT_SUPERADMIN_ALL_LOGINS_ENABLED=false`,
recreate only the UAT backend, revoke active `superadmin` refresh sessions, and
continue permission testing with the named UAT role personas. Production must
keep this switch false or absent.
