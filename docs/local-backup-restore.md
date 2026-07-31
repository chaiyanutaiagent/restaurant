# Local Backup and Restore

Use this before wider pilot testing, risky seed runs, or manual UAT sessions. The backup contains local PostgreSQL data, uploaded files, and Redis operational state for the Docker Compose project.

## What Is Backed Up

- PostgreSQL: custom-format `pg_dump` from the `postgres` service.
- Uploads: local Docker `uploads` volume mounted at `/app/uploads`.
- Redis: `/data` volume after `redis-cli SAVE`.
- Manifest: timestamp, compose project name, service names, and backup contents.

## Run a Local Backup

Make sure `.env` exists, then run:

```sh
./scripts/backup-local.sh
```

The backup is written to `backups/restaurant-pos-local-<timestamp>/`.

To write under another directory:

```sh
./scripts/backup-local.sh /secure/backups/restaurant-pos-local
```

## Restore Locally

Restore replaces the local PostgreSQL database, uploads, and Redis data for the current Compose project.

```sh
./scripts/restore-local.sh backups/restaurant-pos-local-YYYYMMDDTHHMMSSZ
```

The script requires typing `RESTORE` before it proceeds. For an automated local restore drill:

```sh
./scripts/restore-local.sh --yes backups/restaurant-pos-local-YYYYMMDDTHHMMSSZ
```

## Restore Drill Without Touching Current Local Volumes

Use an isolated Compose project name:

```sh
COMPOSE_PROJECT_NAME=restaurant-pos-local-drill ./scripts/restore-local.sh --yes backups/restaurant-pos-local-YYYYMMDDTHHMMSSZ
COMPOSE_PROJECT_NAME=restaurant-pos-local-drill docker compose -f docker-compose.yml ps
COMPOSE_PROJECT_NAME=restaurant-pos-local-drill docker compose -f docker-compose.yml down -v
```

## Notes

- Backups are ignored by Git through `backups/`.
- `.env` and secrets are not backed up.
- Uploads are now stored in a named Docker volume for local runs, matching the production persistence model.
- Restored uploads default to owner `100:101`, matching the backend image's app user. Override with `LOCAL_UPLOADS_OWNER` only if the backend image user changes.
- Redis is useful for continuity during a restore drill, but PostgreSQL and uploads are the durable application data.

## Phase 1 Database Boundary Backup

After running `./scripts/setup-local-database-boundary.sh`, create independent
Platform and Restaurant dumps with:

```sh
./scripts/backup-local-database-boundary.sh
```

This produces `platform-core.dump` and `restaurant.dump`; it intentionally does
not replace the legacy full backup above while data cutover is pending. Verify a
backup by restoring both dumps into isolated drill databases:

```sh
BOUNDARY_DRILL_SUFFIX=verify01 BOUNDARY_DRILL_CLEANUP=1 \
  ./scripts/restore-local-database-boundary-drill.sh \
  backups/restaurant-boundaries-local-YYYYMMDDTHHMMSSZ
```

## Phase 1 Data Cutover Rehearsal

The rehearsal stops the local backend writer, backs up the authoritative legacy
database and both boundary targets, recreates only the two boundary targets,
restores a common source snapshot, prunes Platform operational tables and checks
row parity. The legacy database remains the runtime system of record.

```sh
./scripts/rehearse-local-data-cutover.sh --yes
```

The command prints the rehearsal backup directory. Roll back only the two target
databases to their pre-rehearsal state with:

```sh
./scripts/rollback-local-data-cutover-rehearsal.sh --yes \
  backups/p1-data-cutover-04-YYYYMMDDTHHMMSSZ
```

Both scripts refuse to recreate databases unless the legacy, Platform and
Restaurant database names are distinct. Runtime routing must not be switched to
the rehearsal targets until an outbox-backed reference projection is available.
