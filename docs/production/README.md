# Production Deployment Architecture

This directory contains documentation and templates for production readiness of the Restaurant POS project.

## Intended production architecture

The Restaurant POS production deployment is expected to consist of:

- `backend`
  - FastAPI application running as a production service
  - PostgreSQL for relational data
  - Redis for caching, Celery message broker, and background task state
  - Optional Celery worker service for asynchronous jobs
- `frontend`
  - React/Vite app built into static assets
  - Static assets served by `nginx` in production instead of the Vite development server
- `nginx`
  - Reverse proxy for `/api/` and `/webhooks/`
  - TLS termination for public traffic
  - Static asset hosting for the frontend
- Persistent storage
  - PostgreSQL and Redis data volumes
  - Uploads directory or external object storage for file uploads
- Configuration
  - Environment-specific `.env` values
  - Separate production environment file `.env.production.example`

## What this PR covers

This PR prepares Git repository safety and lightweight CI checks while leaving frontend runtime, backend business behavior, production deploy/rollback behavior, migration behavior, backup/restore behavior, HTTPS activation behavior, and centralized observability behavior unchanged.

- Tightens ignore rules for local caches, generated files, secrets, certs, backups, uploads, logs, and release manifests
- Adds a lightweight GitHub Actions workflow for shell, frontend, backend compile, Docker build, Compose config, and repository safety checks
- Documents safe Git initialization and future registry publishing preparation

## Frontend production build

The frontend is a React/Vite static app. Its production Dockerfile installs dependencies with `npm ci`, runs `npm run build`, and serves the generated `dist` assets from `nginx:alpine` with a minimal SPA fallback for client-side routes. The production image does not run the Vite development server.

## Backend production runtime

The backend is a FastAPI app served by uvicorn. Its production Dockerfile sets `PYTHONUNBUFFERED=1` and `PYTHONDONTWRITEBYTECODE=1`, installs dependencies from `requirements.txt`, runs as a non-root `app` user, and starts with `uvicorn app.main:app --host 0.0.0.0 --port 8000` without development reload. Runtime configuration should be injected through environment variables or a secret manager, not baked into the image.

## Running the production stack

Create a local production environment file from the example, replace all placeholder values with real deployment values, validate it, then deploy the stack:

```sh
cp .env.production.example .env.production
./scripts/check-production-env.sh .env.production
RELEASE_VERSION=2026.06.04-1 ./scripts/deploy-production.sh .env.production
./scripts/smoke-production.sh .env.production
```

The deploy script validates Compose config, creates a backup, builds release-tagged images, runs the explicit migration workflow, starts services, checks production readiness, runs smoke tests, and writes a release manifest. The smoke script verifies health/readiness and the frontend root. Manual equivalents remain available for incident response and debugging.

After startup, verify nginx and the backend health routes:

```sh
curl http://localhost/
curl http://localhost/health
curl http://localhost/health/live
curl http://localhost/health/ready
```

Stop the stack with:

```sh
docker compose -f docker-compose.prod.yml down
```

Do not commit `.env.production`; keep real secrets in local files or a secret manager.

See [deploy-runbook.md](./deploy-runbook.md) for the full production deploy flow, pre-deploy checklist, failure handling, and rollback criteria.

See [vps-manual-deploy.md](./vps-manual-deploy.md) for a manual VPS deployment dry-run path that does not require GitHub Actions or GHCR.

See [rollback-runbook.md](./rollback-runbook.md) for app-only rollback, destructive data restore rollback, nginx config rollback, and post-rollback checks.

See [releases.md](./releases.md) for release tag strategy, release manifests, and app image rollback.

See [git-ci.md](./git-ci.md) for safe Git initialization, ignored-file verification, lightweight CI checks, and future registry publishing notes.

See [first-git-commit.md](./first-git-commit.md) for the pre-Git safety script, first commit review flow, GitHub remote setup, first push, and GitHub Actions verification steps.

See [registry-release.md](./registry-release.md) for the manual GHCR image publishing workflow and release artifact usage.

See [registry-deploy.md](./registry-deploy.md) for optional registry pull deploy and rollback.

See [security-hardening.md](./security-hardening.md) for the final dependency audit, production hardening review, accepted risks, and go-live blockers.

See [uat-smoke-test.md](./uat-smoke-test.md) for automated smoke tests, optional auth smoke, manual business UAT, and sign-off guidance.

## Final go-live and handoff

Before internet-facing launch, complete the final operational handoff package:

- [go-live-checklist.md](./go-live-checklist.md): final technical, DNS, TLS, env/secrets, backup, migration, deploy, smoke/UAT, security risk, rollback, monitoring, and go/no-go checks.
- [operator-handoff.md](./operator-handoff.md): daily/weekly/monthly operator routines, routine commands, data locations, common maintenance tasks, accepted risks, and escalation placeholders.
- [incident-quick-guide.md](./incident-quick-guide.md): short first-response playbooks for health, dependency, deploy, migration, rollback, upload, TLS, disk, backup, and registry pull incidents.
- [sign-off.md](./sign-off.md): placeholder sign-off records for UAT, security risk acceptance, backup/restore drill, operator handoff, and final approval.

See [backup-restore.md](./backup-restore.md) for the production backup and restore workflow, including restore drills and retention guidance.

See [migrations.md](./migrations.md) for the full production migration workflow, including first deploy, upgrade deploy, rollback notes, and backup warnings.

See [uploads.md](./uploads.md) for upload persistence, file type limits, security notes, and manual verification commands.

See [observability.md](./observability.md) for status checks, log commands, request ID tracing, alert recommendations, and the future metrics plan.

See [tls-certbot-host.md](./tls-certbot-host.md) for host-level Certbot setup, HTTPS activation, renewal hooks, and verification commands.

See [restaurant-domain-setup.md](./restaurant-domain-setup.md) for generic
public DNS, tunnel, TLS, production environment, Android build, and go-live
guidance.

## Production env validation

Run the validation script before starting production services. It defaults to `.env.production`:

```sh
./scripts/check-production-env.sh
```

Pass a path to check another file:

```sh
./scripts/check-production-env.sh .env.production
```

The script fails when required variables are missing, placeholder values remain, `ENVIRONMENT` is not `production`, `DEBUG=true`, `SECRET_KEY` is too short, `POSTGRES_PASSWORD` or `DEFAULT_ADMIN_PASSWORD` is weak, wildcard CORS is enabled, `ENABLE_API_DOCS` is not `true` or `false`, `PUBLIC_BASE_URL` or `SERVER_NAME` is empty, or certificate/private-key files are found inside the repository.

Before go-live, review [security-hardening.md](./security-hardening.md), run `./scripts/run-backend-regression.sh`, resolve or formally accept the listed dependency findings, and confirm `ENABLE_API_DOCS=false` for internet-facing production. With production docs disabled, `/api/docs`, `/api/redoc`, and `/api/openapi.json` should return 404 unless explicitly enabled for staging or operator-only environments.

Common failures usually mean the copied example file was not fully customized:

- `placeholder value`: replace `example.com`, `enter_secure_password_here`, `replace_with_secure_random_hex_string`, and any `change_me` values.
- `ENVIRONMENT must be production`: set `ENVIRONMENT=production`.
- `DEBUG must not be true`: remove `DEBUG` or set it to `false`.
- `SECRET_KEY must be at least 32 characters`: generate a long random secret.
- `POSTGRES_PASSWORD is weak`: use a strong non-default database password and keep `DATABASE_URL` in sync.
- `DEFAULT_ADMIN_PASSWORD is weak`: use a strong unique bootstrap admin password from a secret source. The backend requires this value when seeding the default admin user during startup.
- `CORS_ORIGINS must not allow wildcard origins`: list exact production origins only.
- `ENABLE_API_DOCS must be true or false`: use `false` for internet-facing production.
- `certificate or private key files were found`: move `.pem`, `.key`, and `.crt` files outside the repository and mount them from the host.

## Health and readiness

The backend exposes three safe health endpoints. They do not include secrets, connection URLs, stack traces, or credentials.

- `/health`: legacy lightweight health response for compatibility.
- `/health/live`: process liveness only; use this to confirm the app can answer HTTP.
- `/health/ready`: production readiness; checks PostgreSQL connectivity, Redis connectivity, and that uploads storage exists and is writable. It returns a non-2xx status when any required dependency is unavailable.

The production backend container healthcheck uses `/health/ready`, so `docker compose -f docker-compose.prod.yml ps` should show `backend` as healthy only after dependencies are available.

Requests include an `X-Request-ID` response header. If a caller provides `X-Request-ID`, the backend echoes it; otherwise the backend generates one for correlation. Backend request logs include the request ID, method, path, status, and duration.

### Integration validation note

Validate the production Compose build and full deploy flow again for this
repository. Use an isolated Compose project, a new dummy environment, and a
fresh database. Confirm `/health`, `/health/live`, `/health/ready`, `/`, backup,
migrations, status checks, smoke tests, rollback, and release manifest
generation without relying on the source project's deployment history.

## Operational logs

View recent service logs with:

```sh
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 nginx
docker compose -f docker-compose.prod.yml logs --tail=100 postgres
docker compose -f docker-compose.prod.yml logs --tail=100 redis
```

Follow logs during an incident with:

```sh
docker compose -f docker-compose.prod.yml logs -f backend nginx
```

Run the combined production status check with:

```sh
./scripts/check-production-status.sh
```

Troubleshoot an unhealthy backend in this order:

1. Run `curl http://localhost/health/ready`.
2. Check `docker compose -f docker-compose.prod.yml ps`.
3. Inspect backend logs with `docker compose -f docker-compose.prod.yml logs --tail=100 backend`.
4. Inspect dependency logs for `postgres` and `redis`.
5. Confirm the uploads volume is mounted and writable.

Do not log production secrets, tokens, passwords, API keys, database URLs, or full authorization headers.

## Uploads

The backend stores uploaded files under `/app/uploads`, mounted from the `uploads` named volume. Production defaults allow JPEG, PNG, and WebP images up to 5 MB. User filenames are not used as storage names; files are written with UUID-based names after extension, MIME type, size, and path safety checks.

Uploads are included in the backup workflow as `uploads.tar.gz`. See [uploads.md](./uploads.md) and [backup-restore.md](./backup-restore.md) before changing upload limits or restoring production data.

## HTTP local production mode

The active nginx production config is `nginx/conf.d/default.prod.conf`. It listens on port 80 and proxies `/health`, `/api/`, `/webhooks/`, and `/uploads/` to the backend while proxying `/` to the frontend. This mode is intended for local production verification and for first boot before certificates exist.

## HTTPS production mode

The HTTPS-ready template is `nginx/conf.d/default.prod.https.template.conf`. It includes:

- HTTP-to-HTTPS redirect for `SERVER_NAME`
- TLS certificate paths under `/etc/letsencrypt/live/${SERVER_NAME}/`
- HSTS only in the HTTPS server block
- the same backend/frontend proxy routes as HTTP mode

To enable HTTPS, provision real certificates outside the repository and run:

```sh
./scripts/enable-production-https.sh .env.production
```

The script validates the environment, checks `/etc/letsencrypt/live/$SERVER_NAME/fullchain.pem` and `/etc/letsencrypt/live/$SERVER_NAME/privkey.pem`, renders the generated HTTPS nginx config, runs Compose config validation, builds nginx with the HTTPS config, runs `nginx -t`, and recreates or reloads nginx safely.

After Certbot renewal, reload nginx with:

```sh
./scripts/reload-production-nginx.sh .env.production
```

The compose file exposes both ports 80 and 443, but the checked-in active HTTP config does not require certificates.

Test nginx configuration inside the container with:

```sh
docker compose -f docker-compose.prod.yml exec nginx nginx -t
```

Verify HTTPS after activation:

```sh
curl -I https://$SERVER_NAME/health
curl https://$SERVER_NAME/health/ready
```

## Service architecture

- `postgres`: private PostgreSQL service with persistent `postgres_data`
- `redis`: private Redis service with persistent `redis_data`
- `backend`: FastAPI service built from `backend/Dockerfile`, tagged with `RELEASE_VERSION`, configured by `.env.production`, with uploads mounted at `/app/uploads`
- `migrate`: one-off Alembic migration service in the `tools` profile, using the release-tagged backend image and `.env.production`
- `frontend`: Vite static frontend built from `frontend/Dockerfile`, tagged with `RELEASE_VERSION`, and exposed only to the production network
- `nginx`: HTTP reverse proxy built from `nginx/Dockerfile.prod`, tagged with `RELEASE_VERSION`, on host port 80, with port 443 reserved for HTTPS mode, routing `/api/`, `/webhooks/`, `/uploads/`, and `/health*` to the backend and `/` to the frontend

## Known limitations

- Certificate issuance remains a host-level operator step; HTTPS activation and nginx reload helpers are provided.
- Release manifests are local ignored files; registry publishing and CI/CD artifacts are not configured yet.
- Lightweight GitHub Actions CI checks and manual registry image publishing are configured, but automatic production deployment is not configured yet.
- Database migrations are explicit one-off commands; automatic rollback verification is not configured yet.
- Backup and restore are explicit operator scripts; scheduling, encryption, and off-site storage are not configured yet.
- Centralized log aggregation, metrics, and alert delivery are not configured yet.
- Upload malware scanning, object storage, quotas, and lifecycle cleanup are not configured yet.
- Redis password wiring is not enabled as a separate setting; the current backend configuration accepts Redis connection URLs, so password support should be represented in `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` when added.
- Full secret management and rotation policy is not configured yet.

## Next steps

The next PR should implement the remaining production deployment behavior:

- certificate issuance or renewal automation
- scheduled encrypted off-site backups and restore monitoring
- centralized logging, metrics, and alerting
- upload malware scanning, object storage, quotas, and lifecycle cleanup
- secrets management, rotation, and deployment-time injection
