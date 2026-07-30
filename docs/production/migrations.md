# Production Database Migrations

Production schema changes are managed with Alembic. Migrations are explicit one-off operations and are not run automatically by the backend container on every startup.

## When to run migrations

Run migrations before starting or upgrading the production application stack whenever a deployment includes backend model or migration changes. Create a fresh production backup before running migrations. Do not run production seed data as part of this command unless a migration file intentionally and safely includes data changes.

## Command

Create and validate `.env.production`, then run:

```sh
./scripts/run-production-migrations.sh .env.production
```

The script validates secrets first, renders the production compose configuration, then runs the `migrate` compose service from the `tools` profile:

```sh
docker compose -f docker-compose.prod.yml --profile tools run --rm --build migrate
```

The `migrate` service waits for healthy PostgreSQL and runs:

```sh
alembic upgrade head
```

## Migration Graph Verification

Before every deployment, confirm the imported migration graph has exactly one
head:

```sh
cd backend
alembic heads
```

Then run the full migration flow against a new isolated database. Do not treat
validation from the source project's database as evidence for this deployment.

## First Deploy Flow

1. Copy `.env.production.example` to `.env.production` on the deployment host.
2. Replace every placeholder with deployment-specific values.
3. Back up PostgreSQL, uploads, and Redis if the stack already contains data.
4. Run `./scripts/check-production-env.sh .env.production`.
5. Run `./scripts/run-production-migrations.sh .env.production`.
6. Start the stack with `docker compose -f docker-compose.prod.yml up -d`.
7. Verify `/health` and the expected application flows.

## Upgrade Deploy Flow

1. Review the Alembic revisions included in the release.
2. Back up PostgreSQL, uploads, and Redis before applying schema changes.
3. Deploy or build the new backend image.
4. Run `./scripts/run-production-migrations.sh .env.production`.
5. Start or restart the application stack only after migrations succeed.
6. Verify health checks and core workflows.

## Rollback Notes

Prefer restoring from a verified database backup for production rollback. Alembic downgrade paths may be incomplete or destructive, so do not assume `alembic downgrade` is safe without reviewing the specific migration files and testing the rollback against a copy of production data.

If an application rollback is needed after a successful schema migration, verify that the older application version is compatible with the migrated schema before restarting it.

## Warnings

- Back up the production database before running migrations.
- See [backup-restore.md](./backup-restore.md) for backup and restore drills.
- Keep `.env.production` and real secrets out of source control.
- Do not run production seed data unintentionally. The migration workflow only runs Alembic.
- Do not start the full application stack if migrations fail.

## Known Limitations

- Scheduled backup automation and off-site storage are not included yet.
- TLS activation automation is not included yet.
- Migration rollback verification is still a manual release responsibility.
- Backend startup may still run application seed helpers after tables exist; this workflow does not change backend startup behavior.
