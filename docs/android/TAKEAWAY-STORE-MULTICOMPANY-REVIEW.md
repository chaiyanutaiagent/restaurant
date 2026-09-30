# Takeaway Store multi company architecture review

Review scope: baseline `c5bcb30` and the isolated hardening candidate. One generic
Store APK can serve multiple companies; a new company does not require a new
binary. Tenant isolation must be enforced by server identity and authorization,
not by hiding menus or encoding a company inside an APK.

## Current boundaries

| Layer | Current implementation | Evidence or limitation |
| --- | --- | --- |
| Business directory | Business code resolves an active Company | `business_directory_service.py`; inactive/unknown-code tests |
| Credentials | Authentication queries the resolved company and username | `AuthService.authenticate_user`; business-code routing test |
| Branch assignment | Server selects active branches of that company and checks Store permissions | `mobile_store_auth.py`; signed dependency tests |
| Session | Signed company/brand/branch/device/surface claims; scoped permission list, no wildcard | `mobile_store_policy.py`, `auth_service.py`, `dependencies.py` |
| Request | Allowlisted method/path plus headers matching signed claims | Two-company authorization tests; no central admin or other product APIs |
| Catalog and stock | Tenant, brand and sale-location predicates; available = on hand minus reserved | Catalog SQL and stock boundary tests; not a new database concurrency benchmark |
| Device storage | Dedicated Store database, company/branch/user-scoped records; unsynced data blocks logout cleanup | `db.ts`, `takeawayOffline.ts`, browser isolation tests |
| Application updates | Generic signed release per environment/package; no tenant payload fields | Shared browser/CLI policy and native URL/certificate gates |

Server token verification remains authoritative. Decoding claims in the client is
only a consistency check. The new subject and business-code checks protect against
mixed/stale login responses; they do not turn client storage into a security boundary.

The manifest has no company identity by design: release channel is an environment
boundary, not a tenant selector. Adding a company ID to it is rejected by the
contract. A company selects its data by authenticated business code and assignment.

## Proposed target model

Keep company as the tenant boundary. Brands and branches belong to one company;
Store users receive explicit branch assignments and a bounded role. Central
kitchen, ERP and platform staff stay on separate surfaces with separate rights.
Shared raw materials across brands are valid only within authorized company and
location boundaries; never aggregate inventory across companies implicitly.

Retain one UAT package and one future Production package, each with its own
trusted release channel. Store no company-specific credentials in application
assets. Use a managed-device policy if stronger tenant/device locking is needed,
instead of building a new APK for every customer.

## Priorities and unresolved risks

| Priority | Work | Why it matters |
| --- | --- | --- |
| P0 before Production | Disable test-login flags; audit test identities; approve production signing and physical/payment acceptance | UAT access and debug certificates are not Production credentials |
| P1 before wider rollout | Isolated database restore and offline forward-rollback rehearsal | Checksums do not prove recovery without lost transactions |
| P1 | Add disposable-PostgreSQL integration cases for concurrent stock/reservation, idempotency collision and tenant-predicate enforcement | Current new tests use mocked result rows and inspect SQL; they do not prove concurrent behavior |
| P1 | Review global idempotency-key uniqueness in stock movements/credit/outbox | `takeaway_stock_movements` uses a globally unique key, and replay lookup is by key alone; cross-tenant key collision may cause denial or misleading replay success, not a certified isolation guarantee |
| P1 | Enforce exact UAT hostname allowlists consistently across all test modes | Current superadmin/QA base-host check uses `uat-` prefix plus configured environment, not a full approved-host list |
| P1 | Review restored JWT expiry/offline authorization and revoked-user offline queues | Offline continuation policy needs explicit business approval; client cache is not live revocation |
| P2 | Consider PostgreSQL RLS and composite tenant foreign keys through a migration plan | Defense in depth against a future missing application predicate; not introduced in this no-migration candidate |
| P2 | Server-side minimum client enforcement with documented offline grace | A client update prompt cannot enforce revocation when the feed is unreachable |
| P2 | Monitor upload recovery, catalog errors, outbox age, role denials and release failures | These checks need an operator and verified alert delivery |

This is a bounded code review, not a certification that every application query,
database relationship or endpoint is tenant safe. No new RLS, schema migration,
company data import, permission seed, secret rotation or runtime flag change was
performed. Broader migrations and operational rehearsals require their own scope.
