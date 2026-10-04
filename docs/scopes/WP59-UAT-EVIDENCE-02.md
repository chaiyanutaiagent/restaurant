# WP59 UAT Evidence — Platform Identity, Team/RBAC and Operator Governance

Date: 2026-09-22
Environment: UAT only
Production: unchanged and not authorized

## Immutable candidate

| Item | Identity |
|---|---|
| Source commit | `57323f1` |
| Source archive SHA-256 | `fffc0cc18ca248d9f574d0e30ed32a0ea5b48856f39760d500f59be72a9ce161` |
| Backend image | `restaurant-pos-backend:wp59-57323f1` |
| Backend image ID | `sha256:8d4345b7436d703875240c68ef7b6c3743e158a5b1b823ad500b3ed0e45a7065` |
| Frontend image | `restaurant-pos-frontend:wp59-57323f1` |
| Frontend image ID | `sha256:09b07b2f32c0c284a52bb552b0a283af5870f19981d352dbceb0713b41d1c246` |
| Public route | `https://uat-pos.foodchainservice.com/` |

## Data protection and migration

- Final pre-deployment backup:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/wp59-before/restaurant-pos-prod-20260922T103205Z`.
- Platform, Legacy, Restaurant, Retail and Takeaway dumps plus Redis and uploads
  were non-empty and received SHA-256 checksums before migration.
- Platform advanced from `p13platform0017` to `p14platform0018`; Restaurant
  remained `p6restaurant0007`, Retail `p13retail0007` and Takeaway
  `p6takeaway0008`.
- The migration is additive. The rollback drill therefore changed application
  images only and did not downgrade schema or restore data.

## Engineering and UAT results

- Frontend production/PWA build passed. Python compile and Alembic offline SQL
  generation passed.
- Focused Local and immutable-image suites passed 18/18, covering Platform Team
  RBAC, Platform authentication/security and Company module access.
- Authenticated UAT journey verified all six canonical roles, owner Team view,
  invitation acceptance, Security permissions, cross-environment denial,
  immediate session revocation and operator deactivation.
- Temporary test operators were deactivated; their active sessions and active
  role assignments were zero after cleanup.
- Browser visual review passed for Platform Login and authenticated Team & Roles
  on desktop and at the 1024x768 tablet breakpoint. Navigation, invite form,
  operator cards, MFA/session/review indicators and role-governance panel were
  present. The first pre-existing browser tab was redirected by a stale Company
  request; a clean tab loaded the correct Platform route and current bundle.
- Public `/`, `/platform/login`, `/platform/invite` and `/platform/team` routes
  returned HTTP 200. Final backend logs contained no traceback, HTTP 500 or
  error pattern.

## Authorization and audit contract

- Platform permissions are server-authoritative and deny by default.
- Role assignments are environment-scoped. UAT identities cannot query
  Production Team data.
- Invitations use hashed, expiring tokens. Access changes increment credential
  version and revoke active sessions immediately.
- Last-active-Platform-Owner protection applies to role revoke and operator
  deactivation.
- Security mutations require reason and request id and emit audit evidence with
  actor roles, environment and before/after state.

## Rollback, restore and Production isolation

- App-only rollback to backend/frontend `wp58-527ba6d` became healthy in 9
  seconds. The UAT compose environment retains the release-version response, so
  immutable image tags and image IDs are the authoritative rollback identity.
- Restore to `wp59-57323f1` became healthy in 9 seconds.
- Final UAT images, routes and all four migration heads matched the WP59
  checkpoint.
- Production backend, frontend, nginx, PostgreSQL, Redis and cloudflared
  container identities matched the pre-deployment checkpoint exactly.

## Open holds

- No Production deployment, Production role assignment or flag activation.
- Real operator MFA enrollment/recovery handoff and physical device acceptance
  remain `UNVERIFIED / HOLD`.
- Invitation email delivery is not enabled; UAT uses the one-time deep link.
- Full repository regression is deferred to the combined Batch B gate after
  WP61, as authorized.
