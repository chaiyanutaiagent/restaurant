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

## Deployment evidence

- Source commit: `fce44bd65c8982cc1a159358bbc7bf9dd1c2f4b5`.
- Source archive SHA-256:
  `132320a126176d2d77014f319591384457e5250b83c1f33aa3345aeba139e959`.
- Backend image: `restaurant-pos-backend:uat-superadmin-fce44bd`, digest
  `sha256:823f246e6eb00c7b7c0349abc3c05170fcbc19f2f448451149cea17da8e80e60`.
- Backend regression: 598 passed.
- Tenant `superadmin` is active and scoped to the configured UAT Company; its
  password hash was synchronized from the separately stored Platform identity
  without exposing or changing the password.
- Tenant automatic login returned `superadmin` on POS, App, Restaurant, Retail
  and Takeaway UAT hosts. Platform automatic login returned `superadmin` with
  the UAT `platform_owner` role.
- Live Store policy resolved Takeaway branch `BKK-01` with 12 allowlisted Store
  permissions and no wildcard permission.
- Production retained its prior image and had no UAT superadmin gate variable.
