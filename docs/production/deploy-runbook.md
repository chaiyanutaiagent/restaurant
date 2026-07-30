# Production Deploy Runbook

Use this runbook for explicit production deployments. The deploy script validates the environment, creates a backup, builds images, runs migrations, starts the stack, and checks readiness.

## Pre-Deploy Checklist

- Confirm the deployment host has the latest reviewed code.
- Confirm `.env.production` exists only on the deployment host.
- Run `./scripts/check-production-env.sh .env.production`.
- Confirm `DEFAULT_ADMIN_PASSWORD` is set from a secret source; backend startup/bootstrap seeding requires it.
- Confirm no certificate, private key, dump, SQL, or backup artifacts are staged for commit.
- Confirm the previous backup and restore drill expectations are understood.
- Review Alembic migration files before deploying.
- Confirm operators know the rollback decision criteria in [rollback-runbook.md](./rollback-runbook.md).

## Deploy Command

```sh
./scripts/deploy-production.sh .env.production
```

The script defaults to `.env.production` when no env path is supplied:

```sh
./scripts/deploy-production.sh
```

To pin a reviewed immutable image tag:

```sh
RELEASE_VERSION=2026.06.04-1 ./scripts/deploy-production.sh .env.production
```

For a registry-published release, first confirm the production server can `docker login ghcr.io`, then deploy in pull mode. Registry usage is optional; local production builds remain supported.

```sh
PRODUCTION_IMAGE_MODE=pull \
IMAGE_REGISTRY=ghcr.io \
IMAGE_NAMESPACE=owner/repository \
RELEASE_VERSION=2026.06.04-1 \
./scripts/deploy-production.sh .env.production
```

See [registry-deploy.md](./registry-deploy.md).

## What The Script Does

1. Selects `RELEASE_VERSION` from the environment or generates a UTC timestamp tag.
2. Validates production secrets and required settings with `scripts/check-production-env.sh`.
3. Validates `docker-compose.prod.yml` with `docker compose config`.
4. Runs `scripts/backup-production.sh` before migrations and application startup.
5. Builds production images in local build mode, or pulls backend/frontend/nginx images in registry pull mode.
6. Runs explicit Alembic migrations through `scripts/run-production-migrations.sh`.
7. Starts the production stack with `docker compose -f docker-compose.prod.yml up -d`.
8. Repeats `scripts/check-production-status.sh` until readiness passes or the retry limit is reached.
9. Runs `scripts/smoke-production.sh`.
10. Writes `releases/$RELEASE_VERSION/release-manifest.txt`.

Backups are written under `backups/` by default. Override the destination root with:

```sh
PRODUCTION_BACKUP_ROOT=/secure/backup/path ./scripts/deploy-production.sh .env.production
```

Release manifests are ignored by Git and must not contain secrets. See [releases.md](./releases.md).

CI registry release artifacts are separate from local deploy manifests. Download them from the `Release Images` workflow run when comparing what CI built with what the server deployed.

## Integration Validation

Run the deploy flow with an isolated Compose project and a new dummy environment
before production. Validation must include environment checks, Compose config,
backup, image build, migrations, startup, status, smoke checks, and release
manifest generation. The dummy environment needs a unique
`DEFAULT_ADMIN_PASSWORD` because fresh-database startup creates the initial
administrator.

## Health And Status Verification

After deploy, verify:

```sh
curl http://localhost/health/live
curl http://localhost/health/ready
./scripts/check-production-status.sh
./scripts/smoke-production.sh .env.production
docker compose -f docker-compose.prod.yml ps
```

For HTTPS deployments, use the public origin:

```sh
PRODUCTION_STATUS_BASE_URL=https://$SERVER_NAME ./scripts/check-production-status.sh
PRODUCTION_SMOKE_BASE_URL=https://$SERVER_NAME ./scripts/smoke-production.sh .env.production
curl https://$SERVER_NAME/health/ready
```

Run the manual UAT checklist in [uat-smoke-test.md](./uat-smoke-test.md) before go/no-go sign-off.

## HTTPS Note

HTTPS activation is separate from deployment. Use [tls-certbot-host.md](./tls-certbot-host.md) and `scripts/enable-production-https.sh` only after host certificates exist. The deploy script does not issue certificates or change TLS mode.

## Common Failure Handling

- Environment validation fails: replace placeholders, fix weak secrets, confirm `DEFAULT_ADMIN_PASSWORD` is present, and rerun validation.
- Compose config fails: fix invalid compose/env interpolation before building.
- Backup fails: do not continue; investigate PostgreSQL, Redis, uploads volume, and disk space.
- Migration fails: do not run `up -d`; inspect migration logs and decide whether to rollback data from the pre-deploy backup. If Alembic reports multiple heads, create and review a merge migration or otherwise resolve the migration graph before rerunning deploy.
- Readiness fails: inspect `docker compose ps`, backend logs, PostgreSQL logs, Redis logs, and uploads permissions.
- Nginx fails: run `docker compose -f docker-compose.prod.yml exec -T nginx nginx -t`.

## When To Roll Back

Consider rollback when:

- `/health/ready` remains non-2xx after investigation.
- A migration causes data or application errors that cannot be fixed forward quickly.
- Core POS workflows fail after deploy.
- Nginx cannot serve traffic after a config change.
- Error rates or restart loops remain elevated.

See [rollback-runbook.md](./rollback-runbook.md) before restoring data.
