# Production Releases

Production app images are tagged with an immutable `RELEASE_VERSION`. Local deploys tag:

- `restaurant-pos-backend:$RELEASE_VERSION`
- `restaurant-pos-frontend:$RELEASE_VERSION`
- `restaurant-pos-nginx:$RELEASE_VERSION`

PostgreSQL and Redis continue to use their explicit base image tags from `docker-compose.prod.yml`.

Registry release publishing can also push:

```text
ghcr.io/<owner>/<repo>/restaurant-pos-backend:$RELEASE_VERSION
ghcr.io/<owner>/<repo>/restaurant-pos-frontend:$RELEASE_VERSION
ghcr.io/<owner>/<repo>/restaurant-pos-nginx:$RELEASE_VERSION
```

See [registry-release.md](./registry-release.md) for the manual GHCR workflow.

## Release Version Strategy

If `RELEASE_VERSION` is not provided, `scripts/deploy-production.sh` generates a UTC timestamp tag such as:

```text
prod-20260604T130000Z
```

Release versions may contain only letters, numbers, dots, underscores, and hyphens.

For an explicit reviewed release:

```sh
RELEASE_VERSION=2026.06.04-1 ./scripts/deploy-production.sh .env.production
```

## Release Metadata

Deploys create an ignored manifest at:

```text
releases/$RELEASE_VERSION/release-manifest.txt
```

The manifest includes the release version, UTC creation time, Compose project name, Compose file, app image tags, backup path, and deploy verification summary. It must not contain secrets or full environment values.

CI registry releases upload a separate GitHub Actions artifact named `release-manifest-$RELEASE_VERSION`. Local manifests are ignored files under `releases/`; CI manifests are workflow artifacts.

List local release manifests:

```sh
find releases -maxdepth 2 -name release-manifest.txt -print | sort
```

Inspect a manifest:

```sh
sed -n '1,120p' releases/2026.06.04-1/release-manifest.txt
```

## Deploy A Specific Release

```sh
RELEASE_VERSION=2026.06.04-1 ./scripts/deploy-production.sh .env.production
```

The deploy script exports `RELEASE_VERSION` before Compose build, migration, startup, status checks, and smoke checks.

## Roll Back To A Previous App Release

```sh
./scripts/rollback-production.sh --release 2026.06.04-1 --app-only .env.production
```

This recreates app services using the selected backend, frontend, and nginx image tags, then runs production status checks. In local mode, target images must exist locally. In registry pull mode, the scripts pull image references computed from `IMAGE_REGISTRY`, `IMAGE_NAMESPACE`, and `RELEASE_VERSION`.

```sh
PRODUCTION_IMAGE_MODE=pull \
IMAGE_REGISTRY=ghcr.io \
IMAGE_NAMESPACE=owner/repository \
./scripts/rollback-production.sh --release 2026.06.04-1 --app-only .env.production
```

Data rollback is separate and destructive:

```sh
./scripts/rollback-production.sh --data-restore backups/restaurant-pos-prod-YYYYMMDDTHHMMSSZ .env.production
```

## Current Limitations

- Registry publishing is manual only and does not deploy production.
- Release manifests are local files and are ignored by Git.
- App image rollback does not downgrade database schema.
- Migration downgrade remains a manual, reviewed operation or a data restore from backup.

## Future CI/CD Recommendation

A future deployment workflow can deploy by registry tag after backup, migration, smoke, and approval gates are designed. This repository does not automatically deploy from CI yet.
