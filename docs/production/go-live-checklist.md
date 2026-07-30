# Final Go-Live Checklist

Use this checklist for the final production go/no-go review. It is documentation-only and should be completed with placeholders replaced in the deployment environment, not in the repository.

## Pre-Go-Live Technical Checklist

- [ ] Reviewed [deploy-runbook.md](./deploy-runbook.md), [rollback-runbook.md](./rollback-runbook.md), [backup-restore.md](./backup-restore.md), [migrations.md](./migrations.md), and [observability.md](./observability.md).
- [ ] Reviewed [vps-manual-deploy.md](./vps-manual-deploy.md) if using the manual VPS dry-run path before CI/GHCR is available.
- [ ] Confirmed the deployment host has the reviewed release source or reviewed registry images.
- [ ] Confirmed `.env.production` exists only on the deployment host and is not committed.
- [ ] Ran `./scripts/check-production-env.sh .env.production`.
- [ ] Ran `./scripts/run-backend-regression.sh` before launch.
- [ ] Confirmed production Compose config validates.
- [ ] Confirmed no certificate, private key, dump, SQL, backup, upload, generated HTTPS config, or generated release manifest artifact is staged for commit.

## DNS / Domain Checklist

- [ ] `SERVER_NAME` is the production hostname only, without scheme or path.
- [ ] `PUBLIC_BASE_URL` uses the expected public origin.
- [ ] DNS points the production hostname to the production host.
- [ ] Firewall allows inbound TCP ports `80` and `443`.
- [ ] `CORS_ORIGINS` lists exact production origins and does not use `*`.

## TLS / HTTPS Checklist

- [ ] Host-level certificates exist outside the repository.
- [ ] `/etc/letsencrypt/live/$SERVER_NAME/fullchain.pem` exists on the host.
- [ ] `/etc/letsencrypt/live/$SERVER_NAME/privkey.pem` exists on the host.
- [ ] Ran `./scripts/enable-production-https.sh .env.production` after certificates were issued.
- [ ] Verified `curl -I https://$SERVER_NAME/health`.
- [ ] Verified `curl https://$SERVER_NAME/health/ready`.
- [ ] Certbot renewal reloads nginx with `./scripts/reload-production-nginx.sh .env.production`.
- [ ] HSTS remains HTTPS-only.

## Env / Secrets Checklist

- [ ] All placeholder values in `.env.production` were replaced on the host.
- [ ] `ENVIRONMENT=production`.
- [ ] `DEBUG` is unset or `false`.
- [ ] `ENABLE_API_DOCS=false` for internet-facing production.
- [ ] `SECRET_KEY`, database password, registry credentials, payment credentials, and smoke-test credentials are not printed or committed.
- [ ] `POSTGRES_PASSWORD` is strong and matches `DATABASE_URL`.
- [ ] `DEFAULT_ADMIN_PASSWORD` is set to a strong unique bootstrap password from a secret source.
- [ ] Registry credentials, if used, are handled by host-level Docker login or host secret storage.

## Backup Checklist

- [ ] Ran `./scripts/backup-production.sh` before migrations and deployment.
- [ ] Backup directory contains `postgres.dump`, `uploads.tar.gz`, `redis.tar.gz`, `redis-backup-note.txt`, and `manifest.txt`.
- [ ] Backup artifacts are stored outside the repository or in an ignored local backup root.
- [ ] Backup artifacts are treated as sensitive business data.
- [ ] Restore drill completed in an isolated `COMPOSE_PROJECT_NAME` environment.
- [ ] Retention and off-host copy expectations are documented and accepted.

## Migration Checklist

- [ ] Reviewed Alembic revisions included in the release.
- [ ] Confirmed a fresh backup exists before running migrations.
- [ ] Ran `./scripts/run-production-migrations.sh .env.production`.
- [ ] Confirmed the `migrate` service exited successfully.
- [ ] Confirmed failed migrations block full application startup.
- [ ] Accepted that app rollback does not automatically downgrade the database schema.

## Deploy Checklist

- [ ] Selected a reviewed `RELEASE_VERSION`.
- [ ] For local build mode, ran `RELEASE_VERSION=<release_version> ./scripts/deploy-production.sh .env.production`.
- [ ] For registry pull mode, confirmed `PRODUCTION_IMAGE_MODE=pull`, registry variables, and host registry login before deploy.
- [ ] Confirmed deploy created a pre-deploy backup.
- [ ] Confirmed deploy ran migrations, status checks, and smoke checks.
- [ ] Confirmed `releases/$RELEASE_VERSION/release-manifest.txt` was generated locally and remains ignored.
- [ ] Confirmed backend, frontend, and nginx run the same reviewed release tag.

## Smoke / UAT Checklist

- [ ] Ran `./scripts/check-production-status.sh`.
- [ ] Ran `./scripts/smoke-production.sh .env.production`.
- [ ] For HTTPS, ran smoke with `PRODUCTION_SMOKE_BASE_URL=https://$SERVER_NAME`.
- [ ] Verified `/health`, `/health/live`, `/health/ready`, and `/`.
- [ ] Completed manual UAT from [uat-smoke-test.md](./uat-smoke-test.md).
- [ ] Verified login, logout, product/category maintenance, upload, POS sale/order, payment status, receipt, stock movement, report visibility, permissions, restart persistence, backup, and restore drill.
- [ ] Recorded UAT result in [sign-off.md](./sign-off.md) or a controlled launch record.

## Security Accepted-Risk Checklist

- [ ] Reviewed [security-hardening.md](./security-hardening.md).
- [ ] Remaining frontend Vite/esbuild dev-server advisory is fixed or formally accepted because production serves static assets from nginx.
- [ ] Content Security Policy is implemented or formally deferred.
- [ ] WeasyPrint/fontconfig cache warnings are fixed or formally accepted as non-blocking after PDF verification.
- [ ] Upload malware scanning, object storage, quotas, and lifecycle cleanup gaps are accepted or assigned.
- [ ] Centralized logs, metrics, and alert delivery gaps are accepted or assigned.
- [ ] Off-site encrypted backup automation gap is accepted or assigned.
- [ ] Monthly dependency and base-image owner is assigned.

## Rollback Readiness Checklist

- [ ] Reviewed rollback criteria in [rollback-runbook.md](./rollback-runbook.md).
- [ ] Previous app release image exists locally or in the configured registry.
- [ ] App-only rollback command has been tested:

```sh
./scripts/rollback-production.sh --release <previous_release_version> --app-only .env.production
```

- [ ] Destructive data restore rollback requires approval and a verified backup directory.
- [ ] Restore command path is understood:

```sh
./scripts/rollback-production.sh --data-restore backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ .env.production
```

- [ ] Post-rollback status, smoke, and manual UAT checks are assigned.

## Monitoring / Observability Checklist

- [ ] Operators can run `./scripts/check-production-status.sh`.
- [ ] Operators can inspect backend, nginx, postgres, and redis logs.
- [ ] Request ID correlation is understood.
- [ ] Disk usage warning and critical thresholds are known.
- [ ] Backup freshness expectations are known.
- [ ] TLS expiry tracking is assigned.
- [ ] Alerting limitations are accepted until a centralized stack is implemented.

## Go / No-Go Decision

```text
release_version:
environment:
base_url:
decision: go/no-go
decision_time_utc:
decision_owner:
required_followups:
rollback_owner:
notes:
```

## Sign-Off Placeholders

```text
uat_owner_name:
uat_owner_date:
security_owner_name:
security_owner_date:
backup_restore_owner_name:
backup_restore_owner_date:
operator_handoff_owner_name:
operator_handoff_owner_date:
final_approver_name:
final_approver_date:
```
