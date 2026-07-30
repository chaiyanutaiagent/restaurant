# Production Operator Handoff

Use this as the day-to-day operator reference after go-live. Keep real contacts, credentials, domains, and customer data out of this file.

## Daily Operator Checklist

- [ ] Run `./scripts/check-production-status.sh`.
- [ ] Confirm `backend`, `postgres`, and `redis` are healthy.
- [ ] Confirm `/health/ready` returns 200 from the expected production origin.
- [ ] Review recent backend and nginx logs for repeated 5xx errors.
- [ ] Confirm disk usage is below the warning threshold.
- [ ] Confirm latest backup age is within the expected recovery point objective.
- [ ] Check for failed deploy, migration, backup, or TLS renewal activity.

## Weekly Operator Checklist

- [ ] Run and review a fresh backup.
- [ ] Inspect backup directory contents and manifest.
- [ ] Review container restart counts.
- [ ] Review available disk capacity for Docker volumes and backups.
- [ ] Review TLS certificate expiry status.
- [ ] Confirm release manifests match the currently deployed release.
- [ ] Review unresolved accepted risks and assigned follow-ups.

## Monthly Operator Checklist

- [ ] Run an isolated restore drill with `COMPOSE_PROJECT_NAME=restaurant-pos-prod-drill`.
- [ ] Review base-image and dependency update needs.
- [ ] Review backup retention and off-host copy status.
- [ ] Review API docs exposure, CORS origins, and nginx security headers.
- [ ] Review upload policy, upload storage growth, and cleanup needs.
- [ ] Review whether centralized logs, metrics, alerting, and malware scanning remain accepted risks.

## Routine Commands

Status check:

```sh
./scripts/check-production-status.sh
```

Logs:

```sh
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 nginx
docker compose -f docker-compose.prod.yml logs --tail=100 postgres
docker compose -f docker-compose.prod.yml logs --tail=100 redis
docker compose -f docker-compose.prod.yml logs -f backend nginx
```

Backup:

```sh
./scripts/backup-production.sh
```

Deploy:

```sh
RELEASE_VERSION=<release_version> ./scripts/deploy-production.sh .env.production
```

Rollback:

```sh
./scripts/rollback-production.sh --release <previous_release_version> --app-only .env.production
./scripts/rollback-production.sh --data-restore backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ .env.production
```

Smoke test:

```sh
./scripts/smoke-production.sh .env.production
PRODUCTION_SMOKE_BASE_URL=https://$SERVER_NAME ./scripts/smoke-production.sh .env.production
```

TLS reload:

```sh
./scripts/reload-production-nginx.sh .env.production
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t
```

## Where Data Lives

- PostgreSQL volume: `postgres_data`, mounted in the `postgres` container at `/var/lib/postgresql/data`.
- Uploads volume: `uploads`, mounted in the `backend` container at `/app/uploads`.
- Redis volume: `redis_data`, mounted in the `redis` container at `/data`.
- Backups directory: `backups/restaurant-pos-prod-<timestamp>/` by default, or `PRODUCTION_BACKUP_ROOT` when provided.
- Release manifests: `releases/$RELEASE_VERSION/release-manifest.txt`, ignored by Git and expected to contain no secrets.
- TLS certificates: host-level LetsEncrypt path, mounted read-only into nginx when HTTPS is enabled; certificates must stay outside the repository.

## Common Maintenance Tasks

- Before deploy, review the release, run env validation, confirm backup readiness, and set a reviewed `RELEASE_VERSION`.
- After deploy, run status, smoke, and manual UAT checks.
- Before migrations, review Alembic revisions and create a fresh backup.
- After certificate renewal, reload nginx and verify HTTPS health.
- Before data restore, stop application traffic, confirm approval, and verify the backup directory.
- For upload storage growth, inspect volume usage and plan cleanup or object storage migration before capacity pressure.
- For registry deploys, confirm host `docker login`, image namespace, and release tags before pull mode.

## Accepted Risks Operators Should Know

- App image rollback does not automatically downgrade database schema.
- Backups and restores are explicit operator scripts; scheduled encrypted off-site backup automation is not included.
- Centralized log aggregation, metrics, and alert delivery are not configured.
- Uploads are image-restricted but not malware-scanned.
- Uploaded files are stored in a local Docker volume, not object storage.
- Release manifests are local ignored files, not centralized deployment records.
- Registry deploy mode relies on host-level Docker login and does not store registry credentials in `.env.production`.
- Remaining security accepted risks should be reviewed in [security-hardening.md](./security-hardening.md) and [sign-off.md](./sign-off.md).

## Escalation Placeholders

```text
primary_operator_name:
secondary_operator_name:
technical_owner_name:
business_owner_name:
security_owner_name:
hosting_provider_support_channel:
registry_support_channel:
incident_record_location:
```
