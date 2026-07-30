# Production Readiness Checklist

## Docker / deployment

- [ ] Add an explicit production compose file and keep it separate from development compose
- [ ] Use `version: "3.9"` or newer in compose files
- [ ] Define production image builds or pre-built image tags
- [ ] Avoid `--reload` and dev-only settings in production containers
- [ ] Use healthchecks and container restart policies
- [ ] Keep network and service dependencies explicit
- [ ] Avoid bind mounts for production runtime config unless intended
- [ ] Use `./scripts/deploy-production.sh .env.production` for standard deploys
- [ ] Confirm deploy creates a backup before migrations and application startup
- [ ] Confirm deploy runs the explicit migration script
- [ ] Confirm Alembic has one deployable migration head
- [ ] Confirm deploy runs production status checks before success
- [ ] Set an explicit `RELEASE_VERSION` for reviewed production deploys
- [ ] Confirm backend, frontend, and nginx images are tagged with the same `RELEASE_VERSION`
- [ ] Confirm `releases/$RELEASE_VERSION/release-manifest.txt` is generated after deploy
- [ ] Confirm release manifests do not contain secrets or full env values
- [ ] Confirm generated release manifests are not committed
- [ ] Review [deploy-runbook.md](./deploy-runbook.md) before launch
- [ ] Review [rollback-runbook.md](./rollback-runbook.md) before launch
- [ ] Review [releases.md](./releases.md) before launch
- [ ] Confirm rollback decision owners and approval path are defined
- [ ] Confirm app rollback to a previous `RELEASE_VERSION` has been tested
- [ ] Confirm rollback target images exist locally or in a registry
- [ ] Confirm destructive data restore rollback requires a backup directory
- [ ] Confirm post-rollback status and smoke checks are documented
- [ ] Confirm `.github/workflows/ci.yml` passes before release
- [ ] Confirm CI builds backend, frontend, and nginx images
- [ ] Confirm CI validates production Compose config with dummy safe env values
- [ ] Confirm CI checks shell syntax for `scripts/*.sh`
- [ ] Confirm `Release Images` workflow is manual only
- [ ] Confirm release image workflow publishes backend, frontend, and nginx to GHCR with the same `release_version`
- [ ] Confirm release image workflow uploads a release manifest artifact
- [ ] Confirm release image workflow does not deploy to production
- [ ] Confirm GHCR package write permissions are enabled for GitHub Actions
- [ ] Confirm production server has GHCR read access before registry-based rollback
- [ ] Confirm registry release images can be pulled directly with `PRODUCTION_IMAGE_MODE=pull`
- [ ] Confirm `IMAGE_REGISTRY`, `IMAGE_NAMESPACE`, and `RELEASE_VERSION` are set for registry deploys
- [ ] Confirm registry deploy runs backup, migration, status, and smoke checks
- [ ] Confirm registry rollback to a previous release has been tested
- [ ] Confirm local build-mode isolated deploy validation passes backup, image build, migration, app startup, status checks, smoke checks, and release manifest generation

## Frontend

- [ ] Build static assets with `npm run build`
- [ ] Serve the built `dist` folder from `nginx`
- [ ] Remove or disable Vite dev server in production
- [ ] Keep PWA/service worker config compatible with production
- [ ] Ensure asset caching is configured safely

## Backend

- [ ] Use production FastAPI server settings (no `--reload`)
- [ ] Set worker count and host binding explicitly
- [ ] Ensure the backend reads production environment variables
- [ ] Confirm `/health` remains backward compatible
- [ ] Confirm `/health/live` returns process liveness
- [ ] Confirm `/health/ready` checks PostgreSQL, Redis, and uploads
- [ ] Confirm `/health/live` and `/health/ready` pass in an isolated Compose validation
- [ ] Confirm readiness responses do not expose secrets, URLs, stack traces, or credentials
- [ ] Keep `SECRET_KEY` and other secrets out of source control
- [ ] Use the explicit production migration workflow before backend startup
- [ ] Keep migrations as one-off deployment operations, not automatic backend startup work
- [ ] Verify upload directory is writable and persistent

## Database / Redis

- [ ] Use persistent volumes for PostgreSQL and Redis
- [ ] Keep strong production credentials and do not use defaults
- [ ] Use separate Redis databases for cache, Celery broker, and Celery results if needed
- [ ] Ensure database connection strings do not expose secrets in repository
- [ ] Run `./scripts/run-production-migrations.sh .env.production` before production `up`
- [ ] Confirm the `migrate` compose service exits successfully
- [ ] Confirm Alembic has a single deployable head before running `./scripts/deploy-production.sh`
- [ ] Review Alembic migration files before each production release
- [ ] Back up the database before applying migrations
- [ ] Run `./scripts/backup-production.sh` before production migrations
- [ ] Confirm production seed data is not run unintentionally during migration

## Uploads / storage

- [ ] Persist the uploads directory in production
- [ ] Confirm `UPLOAD_DIR=/app/uploads` in production
- [ ] Confirm `uploads` is mounted at `/app/uploads`
- [ ] Confirm `/app/uploads` is writable by the non-root backend user
- [ ] Enforce maximum upload size
- [ ] Restrict upload extensions to reviewed safe types
- [ ] Restrict upload MIME types to reviewed safe types
- [ ] Reject dangerous extensions such as `.exe`, `.sh`, `.php`, `.js`, and `.html`
- [ ] Reject path traversal upload filenames
- [ ] Store uploads with generated UUID filenames
- [ ] Confirm nginx `client_max_body_size` matches backend upload size limits
- [ ] Confirm nginx keeps directory listing disabled for `/uploads/`
- [ ] Confirm uploads are covered by backup and restore drills
- [ ] Consider external object storage for larger production workloads
- [ ] Protect uploaded files from unauthorized access
- [ ] Clean up old files or use lifecycle policies if needed

## Security

- [ ] Do not commit production secrets
- [ ] Review [security-hardening.md](./security-hardening.md) before go-live
- [ ] Run frontend `npm audit --audit-level=moderate`
- [ ] Confirm any remaining npm audit findings are fixed or formally accepted
- [ ] Run a backend dependency audit with Python 3.11
- [ ] Confirm backend audit findings are fixed or formally accepted
- [ ] Run `./scripts/run-backend-regression.sh`
- [ ] Confirm backend regression checks pass in CI
- [ ] Confirm FastAPI/Starlette remediation remains compatible with health, auth, uploads, and API routes
- [ ] Confirm WeasyPrint PDF generation still works after remediation
- [ ] Confirm JWT tokens still encode/decode after the PyJWT migration
- [ ] Confirm `python-jose`/`pyasn1` are no longer installed in the backend image
- [ ] Confirm Docker base images avoid `latest` and have an update policy
- [ ] Confirm `ENABLE_API_DOCS=false` for internet-facing production
- [ ] Confirm `/api/docs`, `/api/redoc`, and `/api/openapi.json` return 404 in production
- [ ] Enable API docs only in development, staging, or operator-restricted environments
- [ ] Confirm HSTS remains HTTPS-only
- [ ] Confirm nginx security headers are present
- [ ] Confirm upload size limits match backend and nginx
- [ ] Confirm no `.env.production`, certs, keys, dumps, SQL files, backups, or generated release manifests are present
- [ ] Confirm the workspace is a Git repository only after reviewing ignored files
- [ ] Run `git status --short --ignored` before the first commit
- [ ] Run `git add --dry-run .` before the first commit
- [ ] Confirm `.env.production` is ignored and absent from commits
- [ ] Confirm generated release manifests under `releases/*` are ignored
- [ ] Confirm CI rejects committed certs, private keys, dumps, SQL files, backups, uploads, and generated HTTPS config
- [ ] Review [git-ci.md](./git-ci.md) before adding a GitHub remote
- [ ] Review [first-git-commit.md](./first-git-commit.md) before running `git init`
- [ ] Run `./scripts/pre-git-safety-check.sh` before `git init`
- [ ] Confirm `.env.example` and `.env.production.example` exist before the first commit
- [ ] Confirm local `.env` is ignored and not staged
- [ ] Confirm `git add --dry-run .` does not include forbidden artifacts
- [ ] Confirm `git remote add origin ...` is run only after first-commit contents are reviewed
- [ ] Confirm `git push -u origin main` is run only after the remote and commit are reviewed
- [ ] Confirm the first GitHub Actions CI run completes after the first push
- [ ] Review [registry-release.md](./registry-release.md) before enabling GHCR release publishing
- [ ] Review [registry-deploy.md](./registry-deploy.md) before enabling registry pull mode
- [ ] Copy `.env.production.example` to `.env.production` only on the deployment host
- [ ] Run `./scripts/check-production-env.sh .env.production` before production startup
- [ ] Confirm `.env.production.example` fails validation until placeholders are replaced
- [ ] Confirm all required production environment variables are present
- [ ] Replace every placeholder value before running production services
- [ ] Use strong random values for `SECRET_KEY`
- [ ] Use a strong non-default `POSTGRES_PASSWORD`
- [ ] Use a strong unique `DEFAULT_ADMIN_PASSWORD` for backend startup/bootstrap seeding
- [ ] Restrict `CORS_ORIGINS` to production domains
- [ ] Confirm `PUBLIC_BASE_URL` and `SERVER_NAME` match the production domain
- [ ] Keep certificates and private keys outside the repository
- [ ] Enable TLS in production and redirect HTTP to HTTPS
- [ ] Confirm DNS `A` record points `SERVER_NAME` to the production host
- [ ] Confirm firewall allows inbound TCP ports `80` and `443`
- [ ] Issue host certificates with Certbot before enabling HTTPS
- [ ] Confirm `/etc/letsencrypt/live/$SERVER_NAME/fullchain.pem` exists on the host
- [ ] Confirm `/etc/letsencrypt/live/$SERVER_NAME/privkey.pem` exists on the host
- [ ] Run `./scripts/enable-production-https.sh .env.production`
- [ ] Confirm generated HTTPS nginx config is not committed
- [ ] Run `curl -I https://$SERVER_NAME/health`
- [ ] Run `curl https://$SERVER_NAME/health/ready`
- [ ] Configure Certbot renewal to call `./scripts/reload-production-nginx.sh .env.production`
- [ ] Use secure headers via `nginx`
- [ ] Limit exposed management endpoints as appropriate

## Monitoring / logging

- [ ] Run `./scripts/check-production-status.sh` after production startup
- [ ] Send logs to stdout/stderr from containers
- [ ] Enable application logging for errors and requests
- [ ] Use `/health/ready` for the backend production container healthcheck
- [ ] Confirm `docker compose -f docker-compose.prod.yml ps` shows backend healthy when dependencies are healthy
- [ ] Confirm `/health/ready` returns non-2xx when a required dependency is unavailable
- [ ] Verify `X-Request-ID` is present for request correlation
- [ ] Confirm backend request logs include `request_id`
- [ ] Document backend, nginx, postgres, and redis log commands
- [ ] Track container restart counts
- [ ] Track disk usage warning above 80 percent and critical above 90 percent
- [ ] Track backup freshness against the recovery point objective
- [ ] Define alert rules for readiness, restart loops, postgres, redis, disk, backups, TLS expiry, migrations, and 5xx errors
- [ ] Confirm operators know not to log secrets, tokens, passwords, API keys, database URLs, or authorization headers
- [ ] Consider metrics or observability tooling later

## Backup / restore

- [ ] Back up PostgreSQL with `postgres.dump`
- [ ] Back up uploads with `uploads.tar.gz`
- [ ] Back up or explicitly account for Redis operational data
- [ ] Store backups outside the repository
- [ ] Protect backups as sensitive customer and business data
- [ ] Define backup retention policy
- [ ] Add restore verification process
- [ ] Run an isolated restore drill with `COMPOSE_PROJECT_NAME`
- [ ] Back up application config and secrets metadata separately
- [ ] Test restore from backups before production launch

## UAT / smoke test

- [ ] Validate container startup and dependencies
- [ ] Confirm `/health` returns healthy status
- [ ] Run `./scripts/smoke-production.sh .env.production` after deploy
- [ ] Run smoke test after rollback
- [ ] Run smoke test after migrations
- [ ] Run smoke test after HTTPS activation
- [ ] Confirm smoke test checks `/health`, `/health/live`, `/health/ready`, and `/`
- [ ] Configure optional auth smoke only with a dedicated UAT user and company ID
- [ ] Confirm smoke tests do not print passwords, tokens, or authorization headers
- [ ] Confirm login and a simple POS transaction flow
- [ ] Confirm logout clears the session
- [ ] Create a UAT category
- [ ] Create a UAT product
- [ ] Upload a UAT product image
- [ ] Edit the UAT product
- [ ] Confirm POS sale/order flow
- [ ] Confirm payment status
- [ ] Confirm receipt view or print
- [ ] Confirm stock movement after sale or adjustment
- [ ] Confirm sales report includes UAT transaction
- [ ] Confirm user/admin permissions
- [ ] Restart stack and confirm data/uploads persist
- [ ] Run backup after a real UAT transaction
- [ ] Run restore drill in an isolated environment
- [ ] Complete pass/fail sign-off in [uat-smoke-test.md](./uat-smoke-test.md)
- [ ] Confirm database migrations run successfully
- [ ] Confirm upload persistence and file access

## Final handoff / go-live

- [ ] Complete [go-live-checklist.md](./go-live-checklist.md) before internet-facing launch
- [ ] Review [vps-manual-deploy.md](./vps-manual-deploy.md) before using a manual VPS dry run while GitHub Actions or GHCR is unavailable
- [ ] Complete DNS/domain, TLS/HTTPS, env/secrets, backup, migration, deploy, smoke/UAT, rollback, and observability checks
- [ ] Record the final go/no-go decision with release version, environment, decision owner, rollback owner, and required follow-ups
- [ ] Review [operator-handoff.md](./operator-handoff.md) with daily, weekly, and monthly operators
- [ ] Confirm operators know status, logs, backup, deploy, rollback, smoke test, and TLS reload commands
- [ ] Confirm operators know where PostgreSQL, uploads, Redis, backups, and release manifests live
- [ ] Review [incident-quick-guide.md](./incident-quick-guide.md) with the incident owner
- [ ] Confirm first-response playbooks exist for backend, frontend, PostgreSQL, Redis, readiness, disk, backup, deploy, migration, rollback, uploads, TLS, and registry pull failures
- [ ] Complete [sign-off.md](./sign-off.md) or an equivalent controlled launch record
- [ ] Confirm UAT sign-off is complete
- [ ] Confirm security risk acceptance is complete
- [ ] Confirm backup/restore drill sign-off is complete
- [ ] Confirm operator handoff sign-off is complete
- [ ] Confirm final go-live approval is complete
- [ ] Confirm sign-off records use placeholder names/dates in the repository and do not include real personal contact details
