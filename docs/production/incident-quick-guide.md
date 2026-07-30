# Production Incident Quick Guide

Use this for first response. Prefer read-only checks first, avoid logging secrets, and move to rollback or escalation when the cue is met.

## Backend Unhealthy

Symptoms: `backend` is unhealthy, restart count increases, `/health/live` or `/health/ready` fails.

First checks: run status, inspect backend logs, then inspect postgres and redis health.

Safe commands:

```sh
./scripts/check-production-status.sh
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml ps
curl http://localhost/health/ready
```

Rollback/escalation cue: rollback if a recent deploy caused the failure and readiness cannot be restored quickly; escalate if logs indicate data corruption, missing secrets, or repeated crashes.

## Frontend Unavailable

Symptoms: `/` returns non-200, nginx cannot reach frontend, static assets fail to load.

First checks: inspect nginx and frontend container status, then verify frontend logs and nginx config.

Safe commands:

```sh
./scripts/check-production-status.sh
docker compose -f docker-compose.prod.yml logs --tail=100 nginx
docker compose -f docker-compose.prod.yml logs --tail=100 frontend
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t
curl -I http://localhost/
```

Rollback/escalation cue: rollback app images if the issue began after deploy; escalate if nginx config or host networking is unavailable.

## PostgreSQL Unhealthy

Symptoms: `postgres` is unhealthy, `/health/ready` fails, backend logs show database connection errors.

First checks: inspect postgres container health, logs, disk usage, and recent backup/restore activity.

Safe commands:

```sh
./scripts/check-production-status.sh
docker compose -f docker-compose.prod.yml logs --tail=100 postgres
docker compose -f docker-compose.prod.yml ps postgres
df -h .
```

Rollback/escalation cue: escalate before destructive restore; use data restore only with approval, a verified backup, and understood data-loss window.

## Redis Unhealthy

Symptoms: `redis` is unhealthy, `/health/ready` fails, backend logs show Redis connection errors.

First checks: inspect redis logs, container status, and disk capacity.

Safe commands:

```sh
./scripts/check-production-status.sh
docker compose -f docker-compose.prod.yml logs --tail=100 redis
docker compose -f docker-compose.prod.yml ps redis
```

Rollback/escalation cue: escalate if Redis cannot start or data restore is being considered; Redis is operational state, while PostgreSQL and uploads are system-of-record data.

## `/health/ready` Failing

Symptoms: `/health/live` passes but `/health/ready` returns non-2xx.

First checks: check postgres, redis, and uploads writability through status and backend logs.

Safe commands:

```sh
curl http://localhost/health/live
curl http://localhost/health/ready
./scripts/check-production-status.sh
docker compose -f docker-compose.prod.yml logs --tail=100 backend
```

Rollback/escalation cue: rollback if readiness failed immediately after deploy and dependencies are otherwise healthy; escalate if storage permissions or database connectivity cannot be restored.

## Disk Usage High

Symptoms: status check warns at 80 percent or higher, backups fail, containers cannot write data.

First checks: inspect filesystem usage and backup/release directories.

Safe commands:

```sh
./scripts/check-production-status.sh
df -h .
find backups -maxdepth 1 -type d -name 'restaurant-pos-prod-*' | sort
find releases -maxdepth 2 -name release-manifest.txt -print | sort
```

Rollback/escalation cue: escalate before deleting business data or backups; free space according to the approved retention policy only.

## Backup Failed

Symptoms: `./scripts/backup-production.sh` exits non-zero or expected backup files are missing.

First checks: validate env, inspect postgres/redis health, check uploads access and disk capacity.

Safe commands:

```sh
./scripts/check-production-status.sh
./scripts/backup-production.sh
docker compose -f docker-compose.prod.yml logs --tail=100 postgres
docker compose -f docker-compose.prod.yml logs --tail=100 redis
df -h .
```

Rollback/escalation cue: do not deploy or migrate without a fresh backup; escalate if backup cannot complete within the release window.

## Deploy Failed

Symptoms: deploy script exits non-zero, status/smoke fails, release manifest is missing.

First checks: read deploy output, run status, inspect backend/nginx logs, confirm backup and migration result.

Safe commands:

```sh
./scripts/check-production-status.sh
./scripts/smoke-production.sh .env.production
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 nginx
```

Rollback/escalation cue: rollback if the current release cannot become ready; escalate if migration or data changes are involved.

## Migration Failed

Symptoms: `./scripts/run-production-migrations.sh .env.production` fails or backend cannot start after schema change.

First checks: inspect migration output and backend logs; confirm the pre-migration backup exists.

Safe commands:

```sh
./scripts/check-production-status.sh
docker compose -f docker-compose.prod.yml logs --tail=100 backend
find backups -maxdepth 1 -type d -name 'restaurant-pos-prod-*' | sort
```

Rollback/escalation cue: do not start the full stack after a failed migration; escalate for corrective migration or approved data restore.

## Rollback Needed

Symptoms: go/no-go decision is no-go, core workflows fail, readiness remains down, or recent deploy caused severe regression.

First checks: identify target release, confirm image availability, confirm backup directory if data restore is needed.

Safe commands:

```sh
./scripts/rollback-production.sh --release <previous_release_version> --app-only .env.production
./scripts/check-production-status.sh
./scripts/smoke-production.sh .env.production
```

Rollback/escalation cue: use app-only rollback first when schema compatibility allows; escalate before destructive data restore.

## Upload Failures

Symptoms: product image upload fails, `/uploads/` access fails, `/health/ready` may fail due to uploads writability.

First checks: inspect backend logs, check upload size/type, confirm uploads volume and nginx size limit.

Safe commands:

```sh
./scripts/check-production-status.sh
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 nginx
docker compose -f docker-compose.prod.yml ps backend
```

Rollback/escalation cue: escalate if uploads volume permissions or data loss is suspected; rollback if the issue began after an app/nginx release.

## TLS Certificate Expired

Symptoms: browser certificate errors, HTTPS checks fail, nginx may still answer HTTP.

First checks: verify host certificate files, run nginx config test, check renewal/reload history.

Safe commands:

```sh
./scripts/reload-production-nginx.sh .env.production
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t
curl -I https://$SERVER_NAME/health
```

Rollback/escalation cue: escalate to the host/TLS owner if certificate renewal failed or files are missing; do not copy certificates into the repository.

## Registry Image Pull Failed

Symptoms: deploy or rollback in pull mode cannot pull backend, frontend, or nginx image.

First checks: confirm host registry login, image namespace, release tag, and package read permissions.

Safe commands:

```sh
docker compose -f docker-compose.prod.yml pull backend frontend nginx
./scripts/check-production-status.sh
```

Rollback/escalation cue: use a locally available release only if approved; escalate if credentials, package visibility, or release tags are wrong.
