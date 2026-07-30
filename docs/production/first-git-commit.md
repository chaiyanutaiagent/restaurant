# First Git Commit Safety

Use this guide from an operator workstation before creating the first repository commit. Do not run `git init`, add a remote, commit, or push from an unattended production host.

## 1. Run Pre-Commit Safety Checks Manually

The local safety script works before Git is initialized:

```sh
./scripts/pre-git-safety-check.sh
```

It checks for forbidden local artifacts, verifies required env example files and production docs exist, and runs shell syntax checks for `scripts/*.sh`. It prints file paths only; it must never print secret values.

Also run the shell syntax check directly:

```sh
sh -n scripts/*.sh
```

## 2. Initialize Git

Only after the safety check passes, initialize Git:

```sh
git init
git branch -M main
```

Do not add a GitHub remote yet. First inspect what Git sees locally.

## 3. Inspect Git Status

Review untracked files:

```sh
git status --short
```

Review ignored files as well:

```sh
git status --short --ignored
```

Expected ignored files may include local env files, logs, uploads, backup directories, generated HTTPS config, generated release manifests, dependency caches, and build output.

## 4. Inspect Ignored Files

Check the most important ignore rules explicitly:

```sh
git check-ignore -v .env
git check-ignore -v .env.production
git check-ignore -v backups/
git check-ignore -v releases/example/release-manifest.txt
git check-ignore -v nginx/conf.d/default.prod.https.conf
git check-ignore -v uploads/
git check-ignore -v backend/uploads/
git check-ignore -v logs/
```

If a path exists and is not ignored, stop and fix `.gitignore` or move the file outside the repository before staging anything.

## 5. Dry-Run The First Add

Preview what would be staged:

```sh
git add --dry-run .
```

This command should not list production env files, certificates, keys, dumps, SQL files, backups, logs, uploads, generated HTTPS config, or generated release manifests.

## 6. Files That Must Never Be Committed

Never commit:

- `.env`
- `.env.production`
- any `.env.*` file except `.env.example` and `.env.production.example`
- certificates and private keys: `*.pem`, `*.key`, `*.crt`
- `letsencrypt/` or `certs/`
- generated HTTPS nginx config: `nginx/conf.d/default.prod.https.conf`
- `backups/`
- `restore-tmp/`
- database and backup artifacts: `*.dump`, `*.sql`, `*.backup.tar.gz`, `*.bak`
- generated release manifests under `releases/*`
- local uploads: `uploads/`, `backend/uploads/`
- local logs: `logs/`, `*.log`
- dependency caches and build output such as `node_modules/`, `dist/`, `.venv/`, and `__pycache__/`

## 7. What To Do If Sensitive Files Appear

If a sensitive file appears in `git status --short` or `git add --dry-run .`:

1. Stop before running `git add .`.
2. Move the file outside the repository or delete the local generated artifact.
3. Update `.gitignore` only if the file pattern should be ignored for everyone.
4. Rerun `./scripts/pre-git-safety-check.sh`.
5. Rerun `git status --short --ignored`.
6. Rerun `git add --dry-run .`.

If a secret was already staged, unstage it without deleting the local file:

```sh
git restore --staged <path>
```

If a secret was already committed, do not push. Rotate the secret and clean the Git history before sharing the repository.

## 8. Create The First Commit

After the dry-run is clean:

```sh
git add .
git status --short
git diff --cached --stat
git commit -m "Prepare production readiness baseline"
```

Review the staged file list before committing. Do not commit automatically from scripts.

## 9. Add A GitHub Remote

Create an empty GitHub repository first. Then add the remote:

```sh
git remote add origin git@github.com:OWNER/REPOSITORY.git
git remote -v
```

Do not use a real remote placeholder in documentation. Replace `OWNER/REPOSITORY` only in the operator shell.

## 10. Push The Main Branch

Push only after the commit and remote are reviewed:

```sh
git push -u origin main
```

Do not push from this PR unless an operator explicitly instructs it later.

## 11. Verify GitHub Actions

After pushing, verify the CI workflow in GitHub:

```sh
gh run list --workflow CI --limit 5
gh run view --log
```

The CI workflow should run repository safety checks, shell syntax checks, frontend install/build, backend regression checks, production env validation with dummy safe values, Compose config validation, and Docker image builds.

The manual `Release Images` workflow should remain manual-only. Do not run it until the release version and GHCR package settings are approved.
