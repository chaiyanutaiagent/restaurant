# Production Observability

This project currently uses lightweight production observability: health endpoints, Docker Compose service status, container logs, request IDs, and backup manifests. A full metrics and alerting stack is intentionally left for a later PR.

## System Status

Run the status check from the deployment host:

```sh
./scripts/check-production-status.sh
```

The script validates `.env.production`, renders the production Compose config, shows service status, checks `/health/live` and `/health/ready`, reports container health and restart counts, prints disk usage, and reports the latest local backup age when `backups/` exists.

For an isolated drill, pass the Compose project name:

```sh
COMPOSE_PROJECT_NAME=restaurant-pos-prod-drill ./scripts/check-production-status.sh
```

The script exits non-zero when readiness fails or required services are unhealthy.

## Logs

View recent logs:

```sh
docker compose -f docker-compose.prod.yml logs --tail=100 backend
docker compose -f docker-compose.prod.yml logs --tail=100 nginx
docker compose -f docker-compose.prod.yml logs --tail=100 postgres
docker compose -f docker-compose.prod.yml logs --tail=100 redis
```

Follow logs during an incident:

```sh
docker compose -f docker-compose.prod.yml logs -f backend nginx
```

Do not log production secrets, access tokens, refresh tokens, passwords, API keys, database URLs, or full authorization headers.

## Request IDs

The backend returns an `X-Request-ID` header. If a client sends `X-Request-ID`, the backend echoes it; otherwise the backend generates one. Backend request logs include `request_id=...`, method, path, status, and duration.

Use the request ID to correlate a user report with backend and nginx logs:

```sh
curl -i http://localhost/health/ready
docker compose -f docker-compose.prod.yml logs --tail=200 backend
```

## Recommended Alerts

- Readiness failure: `/health/ready` returns non-2xx.
- Restart loops: any service restart count increases repeatedly.
- PostgreSQL unhealthy.
- Redis unhealthy.
- Disk usage above 80 percent warning and above 90 percent critical.
- Latest backup older than the expected recovery point objective.
- Failed backup command or missing backup manifest.
- TLS certificate close to expiry.
- Migration command failure.
- Elevated 5xx errors from backend or nginx logs.

## Metrics Plan

Future metrics should include:

- HTTP request count by route/status.
- HTTP error count and 5xx rate.
- Request latency percentiles.
- Health and readiness status.
- Database and Redis connectivity status.
- Disk usage.
- Backup freshness and last backup result.

## Known Limitations

- No centralized log aggregation is configured yet.
- No Prometheus/Grafana stack is configured yet.
- No alert delivery integration is configured yet.
- Status checks are host-run operator commands, not scheduled monitoring.
