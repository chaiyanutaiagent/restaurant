# Restaurant POS v0.1 Production Deployment

This guide prepares Restaurant POS v0.1 for a single Ubuntu 24.04 VPS deployment with
Docker Compose, PostgreSQL, Redis, FastAPI, React/Vite, and Nginx.

## Prerequisites

- Ubuntu 24.04 VPS with at least 2 vCPU and 8 GB RAM.
- Docker Engine and Docker Compose v2.
- Git access to `https://github.com/chaiyanutaiagent/restaurant`.
- A DNS record pointing the production domain to the VPS.
- Open firewall ports:
  - `22/tcp` for SSH from trusted IPs.
  - `80/tcp` for HTTP and certificate issuance.
  - `443/tcp` for HTTPS.
- Enough disk space for Docker images, named volumes, logs, and backups.

## Repository Layout

Production infrastructure entrypoints:

- `docker-compose.prod.yml`: production stack.
- `infra/scripts/backup.sh`: timestamped production backup.
- `infra/scripts/restore.sh`: destructive production restore.
- `infra/docker/`: Docker deployment notes.
- `infra/nginx/`: Nginx deployment notes.
- `infra/backup/`: default local backup destination on the server.
- `nginx/conf.d/`: Nginx production configs.

## Environment Variables

Create the production environment file on the server only:

```sh
cp .env.production.example .env.production
chmod 600 .env.production
```

Set real values for:

- `SERVER_NAME`
- `PUBLIC_BASE_URL`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- `DEFAULT_ADMIN_PASSWORD`
- `CORS_ORIGINS`
- `UPLOAD_DIR`
- upload size/type settings when needed

Do not commit `.env.production` or any secret values.

For an IP-only pilot before DNS and SSL are ready, `PUBLIC_BASE_URL` may
temporarily use `http://` only when this explicit override is set:

```sh
ALLOW_HTTP_PUBLIC_BASE_URL_FOR_PILOT=true
```

Remove this override immediately after domain and SSL setup. Normal production
validation still requires `PUBLIC_BASE_URL` to use `https://`.

Validate before deployment:

```sh
./scripts/check-production-env.sh .env.production
docker compose -f docker-compose.prod.yml config
```

## Docker Deployment

Build and start the production stack:

```sh
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml --profile tools run --rm migrate
docker compose -f docker-compose.prod.yml up -d
```

The stack includes:

- `postgres`
- `redis`
- `backend`
- `frontend`
- `nginx`

Production containers use `restart: unless-stopped`. Persistent data is stored in
named volumes:

- `postgres_data`
- `redis_data`
- `uploads`

## First Startup

After the first `up -d`, verify:

```sh
docker compose -f docker-compose.prod.yml ps
curl http://localhost/health/live
curl http://localhost/health/ready
```

Then open the public domain in a browser and complete UAT smoke tests for:

- Login and branch context.
- Restaurant store order flow.
- Restaurant close-shift and daily central order flow.
- Central approve, pack, ship, and receive flow.
- Franchise credit top-up flow.

## SSL

Start with HTTP until the domain resolves correctly. After DNS is ready, issue
certificates on the host and switch Nginx to the HTTPS production config. Existing
production references are in:

- `docs/production/tls-certbot-host.md`
- `scripts/enable-production-https.sh`

## Backup

Run a timestamped backup:

```sh
infra/scripts/backup.sh
```

By default, backups are written to:

```text
infra/backup/restaurant-pos-prod-YYYYMMDDTHHMMSSZ/
```

Each backup contains:

- `postgres.dump`
- `uploads.tar.gz`
- `redis.tar.gz`
- `manifest.txt`

To write to a separate disk or mounted backup path:

```sh
infra/scripts/backup.sh /secure/backups/restaurant-pos
```

## Restore

Restore is destructive. It replaces PostgreSQL data, uploads, and Redis state for
the selected Compose project.

```sh
infra/scripts/restore.sh infra/backup/restaurant-pos-prod-YYYYMMDDTHHMMSSZ
```

The script requires typing `RESTORE`. For an isolated restore drill:

```sh
COMPOSE_PROJECT_NAME=restaurant-pos-restore-drill \
PRODUCTION_ENV_FILE=.env.production \
infra/scripts/restore.sh --yes infra/backup/restaurant-pos-prod-YYYYMMDDTHHMMSSZ
```

After restore:

```sh
docker compose -f docker-compose.prod.yml up -d
curl http://localhost/health/ready
```

## Troubleshooting

- Compose config fails: check `.env.production` interpolation and missing values.
- Backend unhealthy: inspect `docker compose -f docker-compose.prod.yml logs backend`.
- PostgreSQL unhealthy: inspect credentials, volume space, and `postgres` logs.
- Redis unhealthy: inspect `redis` logs and volume permissions.
- Uploads fail: confirm the `uploads` volume is mounted at `/app/uploads` and writable.
- Nginx fails: run `docker compose -f docker-compose.prod.yml exec -T nginx nginx -t`.
- Disk pressure: prune unused Docker images only after confirming backups exist.
- Migration fails: stop deployment, inspect Alembic output, and decide whether to fix forward or restore from backup.
