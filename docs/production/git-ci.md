# Git And CI Readiness

This workspace may not be a Git repository yet. Do not initialize or push automatically from production hosts. Use these steps from an operator workstation after reviewing the files.

For the full first-commit procedure, use [first-git-commit.md](./first-git-commit.md). Before `git init`, run:

```sh
./scripts/pre-git-safety-check.sh
```

The script does not require a Git repository. It checks for forbidden local artifacts, verifies required example env files and production docs, runs `sh -n scripts/*.sh`, warns about a local `.env`, and exits non-zero if forbidden artifacts are present.

## Initialize Git Safely

Check whether Git is already initialized:

```sh
git status --short
```

If it reports `not a git repository`, initialize locally:

```sh
git init
git branch -M main
```

Inspect ignored and untracked files before the first commit:

```sh
git status --short --ignored
git status --short
```

Review the first commit contents:

```sh
git add --dry-run .
git diff --cached --stat
git diff --cached
```

After review:

```sh
git add .
git commit -m "Prepare production readiness baseline"
```

## Add A GitHub Remote

Create an empty GitHub repository first, then add the remote:

```sh
git remote add origin git@github.com:OWNER/REPOSITORY.git
git remote -v
```

Push only after reviewing local status and confirming no secrets are staged:

```sh
git push -u origin main
```

## Verify Ignored Files

These commands should show ignored local files without staging them:

```sh
git check-ignore -v .env.production
git check-ignore -v backups/
git check-ignore -v releases/example/release-manifest.txt
git check-ignore -v nginx/conf.d/default.prod.https.conf
```

Use a broad safety scan before committing:

```sh
./scripts/pre-git-safety-check.sh
find . -path './.git' -prune -o -type f \( -name '*.pem' -o -name '*.key' -o -name '*.crt' -o -name '*.dump' -o -name '*.sql' \) -print
```

The command should print nothing.

## Never Commit

- `.env`
- `.env.production`
- any `.env.*` file except `.env.example` and `.env.production.example`
- certificates and private keys: `*.pem`, `*.key`, `*.crt`
- `letsencrypt/` or `certs/`
- generated HTTPS nginx config: `nginx/conf.d/default.prod.https.conf`
- `backups/`
- database dumps: `*.dump`, `*.sql`
- generated release manifests under `releases/*`
- local uploads and logs
- restore temp files

## CI Workflow

The lightweight workflow lives at:

```text
.github/workflows/ci.yml
```

It runs on pull requests and pushes to `main` or `master`.

Checks include:

- repository safety scan for forbidden env, cert, backup, dump, SQL, upload, and generated release files
- shell syntax checks for `scripts/*.sh`
- Node 20 setup
- frontend `npm ci`
- frontend `npm run build`
- Python 3.11 setup
- backend `python -m compileall`
- CI-only dummy production env validation
- `docker compose -f docker-compose.prod.yml config`
- backend Docker image build
- frontend Docker image build
- nginx production Docker image build

`npm audit` is intentionally not blocking in this workflow. Add it later only after the dependency baseline is reviewed and known findings are triaged.

## Manual Release Image Workflow

The release image workflow lives at:

```text
.github/workflows/release-images.yml
```

It is manual only through `workflow_dispatch`. It validates `release_version`, builds backend/frontend/nginx images, pushes them to GHCR, and uploads a release manifest artifact. It does not deploy to production.

The workflow uses:

```yaml
permissions:
  contents: read
  packages: write
```

GitHub repository package settings must allow Actions to write packages. Production hosts need GHCR read access before pulling private images.

## Future Registry Publishing

The repository supports immutable local image tags with `RELEASE_VERSION` and a
manual GHCR publishing workflow. Production deployment automation is still
intentionally absent.

A future deployment workflow should:

- deploy by image tag instead of rebuilding on the host
- add backup, migration, health, smoke, and rollback approval gates
- keep production env secrets out of logs

Future GitHub secrets may include only if later deploy automation is approved:

- `REGISTRY_HOST`
- `REGISTRY_USERNAME`
- `REGISTRY_PASSWORD` or token
- deployment host SSH credentials or OIDC configuration
- production environment injection secrets

Do not create real GitHub secrets until the deployment design is reviewed.
