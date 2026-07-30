# Manual VPS Deployment Dry Run

Use this guide to dry-run the production stack on a VPS or VPS-like host without GitHub Actions or GHCR. This path uses local source packaging, local image builds, the existing production scripts, and a host-only `.env.production`.

Do not use this guide to bypass review or approval. It is a temporary manual validation path while GitHub Actions runners are unavailable.

## Server Prerequisites

- Docker Engine installed and running.
- Docker Compose plugin available through `docker compose`.
- A deployment user with permission to run Docker.
- TCP ports `80` and `443` allowed by the host firewall or cloud firewall.
- Sufficient disk space for Docker images, volumes, backups, and release manifests.
- Optional for HTTP dry-run: domain and DNS are not required; the stack can be tested by IP or localhost on the VPS.
- Optional for HTTPS: a real domain, DNS, and host-managed certificates. TLS activation is separate from this dry run.

Verify the server tools:

```sh
docker --version
docker compose version
docker info
```

## Package Source Without Secrets

Package or copy only reviewed source files. Never include local secrets, generated artifacts, backups, uploads, logs, certificates, private keys, dependency caches, or Git metadata.

Example source archive command from the workstation:

```sh
tar \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.env.production' \
  --exclude='.env.local' \
  --exclude='.env.*.local' \
  --exclude='backups' \
  --exclude='releases' \
  --exclude='uploads' \
  --exclude='backend/uploads' \
  --exclude='logs' \
  --exclude='backend/logs' \
  --exclude='*.pem' \
  --exclude='*.key' \
  --exclude='*.crt' \
  --exclude='node_modules' \
  --exclude='frontend/node_modules' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -czf restaurant-source.tar.gz .
```

If you create this archive locally, remove it after transfer or keep it outside the repository. The archive must not be committed.

Example transfer:

```sh
scp restaurant-source.tar.gz deploy-user@vps-host:/opt/restaurant/
ssh deploy-user@vps-host 'cd /opt/restaurant && tar -xzf restaurant-source.tar.gz'
```

Example `rsync` transfer without creating an archive:

```sh
rsync -az --delete \
  --exclude='.git' \
  --exclude='.env' \
  --exclude='.env.production' \
  --exclude='.env.local' \
  --exclude='.env.*.local' \
  --exclude='backups' \
  --exclude='releases' \
  --exclude='uploads' \
  --exclude='backend/uploads' \
  --exclude='logs' \
  --exclude='backend/logs' \
  --exclude='*.pem' \
  --exclude='*.key' \
  --exclude='*.crt' \
  --exclude='node_modules' \
  --exclude='frontend/node_modules' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  ./ deploy-user@vps-host:/opt/restaurant/
```

Use placeholder `deploy-user` and `vps-host` here; replace them only in operator-owned commands, not in repository docs.

## Create Production Env On The VPS

On the VPS, create `.env.production` from the example and edit it on the host only:

```sh
cd /opt/restaurant
cp .env.production.example .env.production
chmod 600 .env.production
```

Required values include:

- `SERVER_NAME`
- `PUBLIC_BASE_URL`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `ENVIRONMENT=production`
- `CORS_ORIGINS`
- `ENABLE_API_DOCS=false` for internet-facing production
- upload, Celery, token, and application settings from `.env.production.example`

Use strong unique values for `SECRET_KEY`, `POSTGRES_PASSWORD`, and `DEFAULT_ADMIN_PASSWORD`. Do not print them in tickets, chat, shell history, logs, or release manifests.

For an HTTP-only dry run, `SERVER_NAME` may be the VPS hostname or a placeholder hostname used only for local testing, but `PUBLIC_BASE_URL` should still be set deliberately and `CORS_ORIGINS` must not use `*`.

## Validate Env And Scripts

Run the safety and env checks on the VPS before deployment:

```sh
sh -n scripts/*.sh
./scripts/pre-git-safety-check.sh
./scripts/check-production-env.sh .env.production
```

The example file should fail validation until placeholders are replaced:

```sh
./scripts/check-production-env.sh .env.production.example
```

## Deploy The Dry-Run Stack

Use local build mode. Do not set `PRODUCTION_IMAGE_MODE=pull`, `IMAGE_REGISTRY`, or `IMAGE_NAMESPACE` for this manual path.

```sh
RELEASE_VERSION=vps-dry-run-YYYYMMDD ./scripts/deploy-production.sh .env.production
```

The deploy script validates env, validates Compose config, creates a pre-deploy backup, builds backend/frontend/nginx images locally, runs migrations, starts the stack, checks status, runs smoke checks, and writes `releases/$RELEASE_VERSION/release-manifest.txt`.

## Smoke And Endpoint Checks

Run the smoke test:

```sh
./scripts/smoke-production.sh .env.production
```

For HTTP dry-run, verify from the VPS or from a workstation that can reach it:

```sh
curl -i http://localhost/
curl -i http://localhost/health
curl -i http://localhost/health/live
curl -i http://localhost/health/ready
```

If testing by server IP:

```sh
curl -i http://vps-host/
curl -i http://vps-host/health/ready
```

For HTTPS mode, first complete [tls-certbot-host.md](./tls-certbot-host.md), then use the public origin:

```sh
PRODUCTION_SMOKE_BASE_URL=https://$SERVER_NAME ./scripts/smoke-production.sh .env.production
curl -i https://$SERVER_NAME/health/ready
```

## App-Only Rollback Dry Run

Test app-only rollback without restoring data:

```sh
RELEASE_VERSION=vps-dry-run-YYYYMMDD ./scripts/rollback-production.sh --app-only .env.production
```

If a previous reviewed release exists, use:

```sh
./scripts/rollback-production.sh --release <previous_release_version> --app-only .env.production
```

Do not run destructive data restore during a simple VPS dry run unless a specific restore drill has been approved.

## Tear Down Dry-Run Stack

For a temporary VPS dry run, stop and remove containers after recording results:

```sh
docker compose -f docker-compose.prod.yml down
```

To remove dry-run volumes too, only when no data must be preserved:

```sh
docker compose -f docker-compose.prod.yml down -v
```

Remove local dry-run backup and release artifacts only after confirming they are not needed:

```sh
rm -rf backups releases
```

Never remove production backups or release manifests casually on a real production host.

## Backup And Restore Cautions

- Backups under `backups/` may contain sensitive customer and business data.
- Release manifests under `releases/` are generated locally and must not contain secrets.
- Restore is destructive; use [backup-restore.md](./backup-restore.md) and require explicit approval.
- App-only rollback does not undo database migrations.
- Keep `.env.production`, backups, uploads, logs, certificates, private keys, and generated release manifests out of source packages and commits.

## TLS, GitHub Actions, And GHCR

TLS is optional for the HTTP dry run and should be activated separately with [tls-certbot-host.md](./tls-certbot-host.md) after certificates exist.

GitHub Actions and GHCR are not required for this manual deployment path. When GitHub runners are available again, prefer CI-validated builds and the reviewed registry release workflow before production launch.
