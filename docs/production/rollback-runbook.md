# Production Rollback Runbook

Rollback is an operator decision. Prefer a small forward fix when it is safer than restoring data. Use data restore only when the impact and data-loss window are understood.

## Decision Criteria

Rollback may be appropriate when:

- `/health/ready` fails after dependency and config checks.
- A deploy breaks login, POS checkout, payments, inventory, or other core workflows.
- A migration creates incorrect data or blocks application startup.
- Nginx config changes prevent traffic from reaching the app.
- The system enters restart loops or cannot recover within the incident window.

## Rollback Types

### App / Container Rollback

Use `--release` to recreate app services with a previous immutable backend/frontend/nginx image tag. The target images must exist locally or be available through a configured registry.

```sh
./scripts/rollback-production.sh --release 2026.06.04-1 --app-only .env.production
```

For registry-published releases, use registry pull mode:

```sh
PRODUCTION_IMAGE_MODE=pull \
IMAGE_REGISTRY=ghcr.io \
IMAGE_NAMESPACE=owner/repository \
./scripts/rollback-production.sh --release 2026.06.04-1 --app-only .env.production
```

The production host must already be logged in to GHCR with package read permission.

Without `--release`, the app-only flow recreates services using the current `RELEASE_VERSION` environment value or the Compose default tag.

```sh
./scripts/rollback-production.sh --app-only .env.production
```

See [releases.md](./releases.md) for image tag and manifest details.
See [registry-deploy.md](./registry-deploy.md) for registry pull mode.

### Data Restore Rollback

Data restore is destructive and remains separate from app image rollback. It restores PostgreSQL, uploads, and Redis by calling the existing restore script. A backup directory is required.

```sh
./scripts/rollback-production.sh --data-restore backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ .env.production
```

For a non-interactive incident run after approval:

```sh
./scripts/rollback-production.sh --data-restore backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ --yes .env.production
```

The restore script still validates backup files and production env before replacing data.

### Nginx Config Rollback

If HTTPS activation or nginx config is the problem, return to the checked-in HTTP production config and rebuild/recreate nginx:

```sh
unset NGINX_PROD_CONF
docker compose -f docker-compose.prod.yml build nginx
docker compose -f docker-compose.prod.yml up -d --no-deps nginx
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t
```

If certificates were renewed and nginx only needs a reload:

```sh
./scripts/reload-production-nginx.sh .env.production
```

## Migration Downgrade Limitations

The production migration workflow runs `alembic upgrade head`. App image rollback does not downgrade the database schema. Automatic migration downgrade and schema rollback are not implemented. If a migration must be reversed, write and review an explicit corrective migration or restore data from a known-good backup after approval.

## Post-Rollback Checks

Run:

```sh
./scripts/check-production-status.sh
./scripts/smoke-production.sh .env.production
curl http://localhost/health/live
curl http://localhost/health/ready
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml ps
```

For HTTPS:

```sh
PRODUCTION_STATUS_BASE_URL=https://$SERVER_NAME ./scripts/check-production-status.sh
PRODUCTION_SMOKE_BASE_URL=https://$SERVER_NAME ./scripts/smoke-production.sh .env.production
curl https://$SERVER_NAME/health/ready
```

Confirm core business flows manually after the system is healthy. Use [uat-smoke-test.md](./uat-smoke-test.md) for the post-rollback smoke and UAT checklist.
