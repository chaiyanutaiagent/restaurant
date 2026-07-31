# Database Boundaries

## Runtime Boundaries

The target architecture uses three explicit connection identities:

| Connection | Responsibility | Scope P1-DATABASE-BOUNDARY-03 |
|---|---|---|
| `DATABASE_URL` | Existing monolith and rollback source | Remains the runtime system of record |
| `PLATFORM_DATABASE_URL` | Company, Brand, Branch, identity, assignments and platform audit | Physical database and independent migration history are initialized |
| `RESTAURANT_DATABASE_URL` | Restaurant masters and operations | Physical database and independent migration history are initialized |

The two explicit URLs fall back to `DATABASE_URL` when absent so older deployments continue to start. A deployment is not considered physically separated while either explicit URL resolves to the legacy URL.

## Initial Ownership Manifest

Platform-owned tables for the data-cutover design:

- `companies`
- `brands`
- `branches`
- `brand_branches`
- `users`
- `roles`
- `permissions`
- `role_permissions`
- `user_branches`
- `refresh_tokens`
- `user_access_requests`
- `user_invitations`
- platform-owned `audit_logs`

Restaurant-owned tables include Restaurant menu/recipe, dining, kitchen, central production, Restaurant stock, purchase, transfer, payment, receipt, accounting and operational audit data. Generic tables currently shared with legacy Retail require an explicit compatibility decision before cutover and must not be moved implicitly.

## Cross-Database Rules

- No SQL foreign key may point across physical databases.
- Restaurant rows retain immutable `company_id`, `brand_id`, `branch_id` and actor IDs as scalar references.
- Authentication and assignment validation use the Platform connection.
- Restaurant writes use only the Restaurant connection in a request transaction.
- Cross-domain propagation must use a versioned API or idempotent outbox/event; a request must not commit one SQLAlchemy transaction across two engines.
- A router moves away from the legacy connection only after its table set, cross-boundary references, migration, rollback and UAT are documented in a separate Scope ID.

## Cutover Sequence

1. Establish and verify independent physical connections, migration histories and backup/restore tooling.
2. Classify every legacy table and foreign key as Platform, Restaurant, Retail compatibility or shared reference projection.
3. Create domain baselines without cross-database foreign keys.
4. Copy and reconcile data while legacy remains authoritative.
5. Route authentication/assignment reads to Platform and one bounded Restaurant workflow to Restaurant.
6. Expand routing only after parity checks; retain rollback to the legacy database until final sign-off.

`P1-DATABASE-BOUNDARY-03` performs step 1 and records the guardrails for step 2.
`P1-DATA-CUTOVER-04` rehearses a consistent snapshot, Platform ownership pruning,
Restaurant operational restore, parity checks and rollback. The legacy database
remains authoritative until an outbox-backed runtime cutover is verified.
`P1-REFERENCE-PROJECTION-05` verifies the outbox-backed reference path and
crash-safe replay. Runtime routing still remains on legacy until Platform writes
enqueue events in the same ownership transaction and one bounded API slice passes
cutover UAT.

## Reference Projection Contract

`P1-REFERENCE-PROJECTION-05` introduces a Platform transactional outbox and a
Restaurant idempotency ledger for Company, Brand, Branch, BrandBranch and User
references. The event envelope contains only aggregate IDs and non-sensitive trace
metadata; the projector reads current state from Platform instead of putting entity
snapshots or credentials in the outbox.

Processing has three independently committed steps: claim on Platform, upsert plus
ledger insert on Restaurant, then acknowledgement on Platform. A crash after the
Restaurant commit replays the event, and the Restaurant `event_id` primary key turns
that replay into a no-op. No transaction or database session is kept open across the
two database writes.

Restaurant preserves its operational `brands.central_location_id`,
`brands.central_ready_location_id` and `brand_branches.store_location_id` columns
when applying Platform references. The transitional Restaurant `users` projection
exists only for operational foreign-key compatibility and must never be used for
authentication.
