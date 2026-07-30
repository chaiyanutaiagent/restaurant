# Restaurant POS Production Checklist

Use this checklist before promoting a new Restaurant POS deployment to
production. All items start unverified because this repository does not inherit
the source project's server, DNS, database, credentials, or validation status.

## Docker

- [ ] Docker Engine installed on Ubuntu 24.04.
- [ ] Docker Compose v2 available with `docker compose version`.
- [ ] `docker compose -f docker-compose.prod.yml config` passes.
- [ ] Production stack includes `frontend`, `backend`, `postgres`, `redis`, and `nginx`.
- [ ] Containers use `restart: unless-stopped`.
- [ ] Named volumes exist for `postgres_data`, `redis_data`, and `uploads`.

## Firewall

- [ ] SSH restricted to trusted IPs where possible.
- [ ] Port `80/tcp` open.
- [ ] Port `443/tcp` open.
- [ ] Database and Redis are not exposed publicly.
- [ ] Host firewall rules are documented.

## SSL

- [ ] Domain resolves to the VPS.
- [ ] Certificates issued for `SERVER_NAME`.
- [ ] Certificate renewal tested or scheduled.
- [ ] Nginx HTTPS config enabled after certificates exist.
- [ ] HTTP to HTTPS redirect verified.

## Domain

- [ ] `SERVER_NAME` matches DNS.
- [ ] `PUBLIC_BASE_URL` uses the final HTTPS origin.
- [ ] `CORS_ORIGINS` lists only approved browser origins.
- [ ] Browser access verified from an external network by IP-only pilot URL.

## PostgreSQL

- [ ] `POSTGRES_PASSWORD` is strong and unique.
- [ ] `DATABASE_URL` matches the production PostgreSQL service.
- [ ] `postgres_data` volume persists across container restart.
- [ ] Alembic migrations run successfully.
- [ ] PostgreSQL is included in backup and restore drills.

## Redis

- [ ] Redis uses persistent `/data` volume.
- [ ] `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` point to Redis.
- [ ] Redis is not exposed publicly.
- [ ] Redis operational state backup policy is understood.

## Backup

- [ ] `infra/scripts/backup.sh` runs successfully.
- [ ] Backup directory contains `postgres.dump`, `uploads.tar.gz`, `redis.tar.gz`, and `manifest.txt`.
- [ ] Backups are stored outside the application working tree or copied to durable storage.
- [ ] Backup retention policy is defined.
- [ ] Backup failure alerts or manual checks are assigned.

## Monitoring

- [ ] `/health/live` and `/health/ready` are checked after deploy.
- [ ] Docker container restart loops are monitored.
- [ ] Disk usage for Docker volumes and backups is monitored.
- [ ] Nginx access/error logs are reviewed.
- [ ] Application error logs are reviewed after UAT and deploy.

## Restore Verification

- [ ] Restore drill completed with an isolated `COMPOSE_PROJECT_NAME`.
- [ ] Restored PostgreSQL data verified.
- [ ] Restored uploads archive extraction verified.
- [ ] Restored Redis archive extraction verified.
- [ ] Application readiness passes in production after permission repair and stack verification.
- [ ] Restore runbook owner is assigned.
