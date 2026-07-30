# Production Backup and Restore

Backups protect customer, inventory, sales, and operational data. Treat every backup artifact as sensitive business data and store it outside the repository with restricted access.

## What Is Backed Up

- PostgreSQL: custom-format `pg_dump` from the `postgres` service.
- Uploads: `uploads` volume mounted at `/app/uploads`.
- Redis: `/data` volume after `redis-cli SAVE`.
- Manifest: timestamp, compose project name, service names, and backup contents.

## What Is Not Backed Up

- `.env.production` and real secrets.
- TLS certificates.
- Container images.
- Nginx logs.
- Host-level operating system configuration.

Redis is used for rate-limit/cache state and Celery broker/result data. Its backup is useful for operational continuity, but PostgreSQL and uploads are the durable system-of-record backups.

See [uploads.md](./uploads.md) for upload persistence, file type limits, and restore safety notes.

## Run a Backup

Create and validate `.env.production`, then run:

```sh
./scripts/backup-production.sh
```

The script defaults to `docker-compose.prod.yml`, `.env.production`, and writes to `backups/restaurant-pos-prod-<timestamp>/`.

To write under another local directory:

```sh
./scripts/backup-production.sh /secure/backups/restaurant-pos
```

The backup directory should contain:

- `postgres.dump`
- `uploads.tar.gz`
- `redis.tar.gz`
- `redis-backup-note.txt`
- `manifest.txt`

`./scripts/check-production-status.sh` reports the latest local backup directory age when `backups/` exists.

## Restore

Restore is destructive. Stop application traffic first, verify the target environment, and restore only from a trusted backup directory:

```sh
./scripts/restore-production.sh backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ
```

The script requires typing `RESTORE` before it replaces PostgreSQL data, uploads, and Redis data. For non-interactive restore drills, pass `--yes`:

```sh
./scripts/restore-production.sh --yes backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ
```

## Restore Drill

Use an isolated Compose project name so the drill does not touch production volumes:

```sh
COMPOSE_PROJECT_NAME=restaurant-pos-prod-drill ./scripts/restore-production.sh --yes backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ
COMPOSE_PROJECT_NAME=restaurant-pos-prod-drill docker compose -f docker-compose.prod.yml ps
COMPOSE_PROJECT_NAME=restaurant-pos-prod-drill docker compose -f docker-compose.prod.yml down -v
```

Run restore drills regularly and after changing backup scripts.

## Before Migrations

Run a fresh backup before production migrations:

```sh
./scripts/backup-production.sh
./scripts/run-production-migrations.sh .env.production
```

Do not apply schema changes unless a recent backup exists and has been restored successfully in a drill.

## Retention

A practical starting policy:

- Keep daily backups for 14 days.
- Keep weekly backups for 8 weeks.
- Keep monthly backups for 12 months.
- Store at least one copy off-host or in managed object storage.
- Periodically test restoring an older backup, not only the newest one.

Adjust retention for legal, tax, and business continuity requirements.

## Known Limitations

- No automated off-site upload is included.
- No encryption-at-rest wrapper is included; use encrypted storage or a secret-managed backup system.
- No scheduled backup timer is included.
- Redis restore replaces operational cache/queue state and may not be appropriate while workers are active.
- Nginx logs are not included in application data backups.
