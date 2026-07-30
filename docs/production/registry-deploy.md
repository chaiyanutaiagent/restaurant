# Registry-Aware Production Deploy

Use registry pull mode when CI has already published immutable release images and the production host should run those exact images instead of rebuilding locally.

Local build mode remains the default and is still appropriate for local production verification or hosts that intentionally build from source.

## Modes

Local build mode:

```sh
RELEASE_VERSION=2026.06.04-1 ./scripts/deploy-production.sh .env.production
```

Registry pull mode:

```sh
PRODUCTION_IMAGE_MODE=pull \
IMAGE_REGISTRY=ghcr.io \
IMAGE_NAMESPACE=owner/repository \
RELEASE_VERSION=2026.06.04-1 \
./scripts/deploy-production.sh .env.production
```

In pull mode, the scripts compute:

```text
BACKEND_IMAGE=$IMAGE_REGISTRY/$IMAGE_NAMESPACE/restaurant-pos-backend:$RELEASE_VERSION
FRONTEND_IMAGE=$IMAGE_REGISTRY/$IMAGE_NAMESPACE/restaurant-pos-frontend:$RELEASE_VERSION
NGINX_IMAGE=$IMAGE_REGISTRY/$IMAGE_NAMESPACE/restaurant-pos-nginx:$RELEASE_VERSION
```

You may also set `BACKEND_IMAGE`, `FRONTEND_IMAGE`, and `NGINX_IMAGE` directly for advanced cases.

## Host Registry Login

Log in on the production host before deploying:

```sh
docker login ghcr.io
```

Use a dedicated read-only GHCR token for the production host when possible. Do not store registry credentials in `.env.production`; use Docker credential storage, host secret management, or an operator login procedure.

## Required Variables

Registry pull mode requires:

```text
PRODUCTION_IMAGE_MODE=pull
IMAGE_REGISTRY=ghcr.io
IMAGE_NAMESPACE=<owner>/<repo>
RELEASE_VERSION=<release_version>
```

`RELEASE_VERSION` may contain only letters, numbers, dots, underscores, and hyphens.

## Deploy From A Registry Release

1. Run the manual `Release Images` workflow in GitHub.
2. Confirm GHCR contains backend, frontend, and nginx images for the chosen `RELEASE_VERSION`.
3. Log in to GHCR on the production host.
4. Run:

```sh
PRODUCTION_IMAGE_MODE=pull \
IMAGE_REGISTRY=ghcr.io \
IMAGE_NAMESPACE=owner/repository \
RELEASE_VERSION=2026.06.04-1 \
./scripts/deploy-production.sh .env.production
```

The deploy script validates env, validates Compose config, pulls app images, runs the existing backup workflow, runs the existing migration workflow, starts services with `--no-build`, checks status, runs smoke tests, and writes local release metadata.

## Roll Back To A Registry Release

```sh
PRODUCTION_IMAGE_MODE=pull \
IMAGE_REGISTRY=ghcr.io \
IMAGE_NAMESPACE=owner/repository \
./scripts/rollback-production.sh --release 2026.06.04-1 --app-only .env.production
```

Rollback pulls the selected backend/frontend/nginx images, recreates app services with `--no-build`, and runs production status checks.

Data restore rollback remains separate and destructive:

```sh
./scripts/rollback-production.sh --data-restore backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ .env.production
```

## Troubleshooting Pull Failures

- Confirm `docker login ghcr.io` succeeds on the production host.
- Confirm the token has package read permission.
- Confirm `IMAGE_NAMESPACE` matches the GitHub owner/repository path.
- Confirm the manual `Release Images` workflow completed successfully.
- Confirm the `RELEASE_VERSION` tag exists for all three images.
- Run `docker pull ghcr.io/<owner>/<repo>/restaurant-pos-backend:<release_version>` manually to isolate credentials or package visibility issues.

## Limitations

- No automatic CI-to-server production deployment is implemented.
- No registry credentials are committed or generated.
- Pull mode still relies on the explicit production backup, migration, status, and smoke workflows.
- App image rollback does not downgrade database schema.
