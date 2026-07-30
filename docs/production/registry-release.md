# Registry Release Images

This workflow prepares immutable registry publishing so release images can be
built once, stored in GitHub Container Registry, and pulled by production hosts
when operators choose to deploy.

No automatic production deployment is configured.

## Why Registry Publishing Matters

Registry-published images make releases easier to reproduce:

- CI builds backend, frontend, and nginx images once.
- Every image gets the same `release_version` tag.
- Production hosts can pull the reviewed release instead of rebuilding locally.
- Rollback can target a previous immutable image tag.

## GHCR Permissions

The manual workflow uses GitHub Container Registry:

```text
ghcr.io/<owner>/<repo>/restaurant-pos-backend:<release_version>
ghcr.io/<owner>/<repo>/restaurant-pos-frontend:<release_version>
ghcr.io/<owner>/<repo>/restaurant-pos-nginx:<release_version>
```

The workflow uses the built-in `GITHUB_TOKEN` and declares:

```yaml
permissions:
  contents: read
  packages: write
```

Repository package settings may need to allow GitHub Actions to write packages. For private repositories, production hosts need credentials with permission to read GHCR packages.

## Run The Manual Workflow

In GitHub:

1. Open `Actions`.
2. Select `Release Images`.
3. Choose `Run workflow`.
4. Enter a `release_version`.
5. Start the workflow.

Release versions may contain only letters, numbers, dots, underscores, and hyphens.

Examples:

```text
2026.06.04-1
v1.0.0
prod-20260604T130000Z
uat_2026_06_04
```

The workflow also tags each image with the Git short SHA as `sha-<shortsha>`.

## Find Pushed Images

After the workflow passes, check the repository or organization Packages page for:

```text
restaurant-pos-backend
restaurant-pos-frontend
restaurant-pos-nginx
```

Expected image references:

```text
ghcr.io/<owner>/<repo>/restaurant-pos-backend:<release_version>
ghcr.io/<owner>/<repo>/restaurant-pos-frontend:<release_version>
ghcr.io/<owner>/<repo>/restaurant-pos-nginx:<release_version>
```

## Release Manifest Artifact

The workflow uploads an artifact named:

```text
release-manifest-<release_version>
```

Download it from the workflow run summary. It records the release version, Git SHA, image namespace, image tags, and workflow name. It must not contain production secrets or full environment values.

Local deploys still create ignored manifests under `releases/$RELEASE_VERSION/`. CI release manifests are GitHub Actions artifacts instead.

## Deploy A Release On The Production Server

Production Compose supports direct registry image variables. After publishing images, log in on the production host and deploy in pull mode:

```sh
RELEASE_VERSION=2026.06.04-1

docker login ghcr.io
PRODUCTION_IMAGE_MODE=pull \
IMAGE_REGISTRY=ghcr.io \
IMAGE_NAMESPACE=<owner>/<repo> \
RELEASE_VERSION="$RELEASE_VERSION" \
./scripts/deploy-production.sh .env.production
```

See [registry-deploy.md](./registry-deploy.md) for the full registry deploy and rollback flow.

## Rollback Concept

To roll back app containers to a previous registry release:

1. Choose the previous `RELEASE_VERSION`.
2. Confirm the production host can pull from GHCR.
3. Run `PRODUCTION_IMAGE_MODE=pull IMAGE_REGISTRY=ghcr.io IMAGE_NAMESPACE=<owner>/<repo> ./scripts/rollback-production.sh --release <previous-version> --app-only .env.production`.
4. Run smoke and UAT checks.

Data restore remains separate and destructive. App image rollback does not downgrade database schema.

## Limitations

- No automatic production deployment from CI.
- No registry credentials or production secrets are created by this PR.
- Registry pull mode requires production host Docker credentials with package read permission.
- Registry image rollback does not replace backup/restore or migration downgrade planning.

## Log Safety

Never print production env files, database URLs, tokens, passwords, private keys, or full authorization headers in GitHub Actions logs. Keep production environment injection out of this workflow.
