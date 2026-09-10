# Production Security Hardening

Run this review before go-live and after each dependency or base-image update. It documents the current risk posture; it does not replace a full penetration test or compliance review.

## Dependency Audit Summary

Run fresh audits for this repository and record the reviewed results before
go-live:

```sh
cd frontend
npm audit --audit-level=moderate

cd ../backend
pip-audit -r requirements.txt
```

Run the backend audit with Python 3.11, matching the backend Dockerfile. Do not
copy vulnerability acceptance or sign-off from the source project.

Reviewed result on 1 August 2026 for `P5-UAT-SECURITY-03`:

- Backend `pip-audit` reports zero known vulnerabilities after upgrading FastAPI/Pydantic,
  replacing `python-jose` with PyJWT 2.13.0, and upgrading python-multipart, WeasyPrint and aiosmtplib.
- Production frontend audit reports two package rows for one React Router RSC-mode CSRF advisory.
  This application uses only declarative `BrowserRouter` in a static CSR bundle; it has no React Router
  Actions, SSR, RSC or server runtime. The production container contains nginx and built assets only.
  Treat this as a reviewed non-reachable finding, but obtain security-owner acceptance before go-live.
- The full frontend audit additionally reports Vite/esbuild development-server findings. Vite and its
  Node toolchain exist only in the build stage and are absent from the production nginx runtime.
- There are no critical npm findings. Re-run both audits at release time because advisory data changes.

Refresh on 10 September 2026 for `P5-POS-TABLET-UX-07`:

- Production-only audit: four package rows (`3 high`, `1 low`).
- Full frontend audit: eleven package rows (`7 high`, `3 moderate`, `1 low`).
- Findings now include updated advisories in React Router, PostCSS/Nanoid and build/mobile tooling.
- No critical finding was reported, but the earlier exception count is no longer current. UAT may continue in its isolated environment; Production release remains pending a scoped dependency update or accountable security-owner review recorded in `security-risk-acceptance.md`.

## Docker Base Image Policy

Production Dockerfiles avoid `latest` tags. Current policy:

- Backend uses `python:3.11-slim`
- Frontend build uses `node:20-alpine`
- Frontend runtime uses `nginx:1.27-alpine`
- Production nginx uses `nginx:1.27-alpine`
- PostgreSQL uses `postgres:15-alpine`
- Redis uses `redis:7-alpine`

Review base images monthly and whenever upstream security advisories are published. Prefer major/minor tags with routine rebuilds, and test image upgrades in an isolated stack before production.

## Production Config Hardening

The production environment validator checks:

- `ENVIRONMENT=production`
- `DEBUG` is not `true`
- required variables are present
- placeholder values such as `example.com`, `change_me`, and `replace_with` are rejected
- `SECRET_KEY` is at least 32 characters
- `POSTGRES_PASSWORD` is not weak/default and is at least 16 characters
- `DEFAULT_ADMIN_PASSWORD` is present, not weak/default, and is at least 16 characters
- `CORS_ORIGINS` is not `*`
- `PUBLIC_BASE_URL` is not empty and should use `https://`
- `SERVER_NAME` is not empty and is hostname-only
- certificate/private-key files are not inside the repository

Production Compose keeps PostgreSQL and Redis on the private Docker network without public host ports. The only exposed production ingress is nginx on ports 80 and 443.

## API Docs And OpenAPI

FastAPI docs are now disabled by default in production. The app exposes `/api/docs`, `/api/redoc`, and `/api/openapi.json` only when API docs are enabled.

- Production `.env.production` should set `ENABLE_API_DOCS=false`.
- Development and test environments keep docs enabled by default when `ENABLE_API_DOCS` is unset.
- Staging can temporarily set `ENABLE_API_DOCS=true` for operator/UAT work, but public internet-facing production should leave it disabled.

## Regression Coverage

Run focused backend regression checks before go-live:

```sh
./scripts/run-backend-regression.sh
```

The regression suite covers:

- PyJWT access token creation and decode
- invalid and expired token rejection
- API docs config defaults for production and non-production
- `/health`, `/health/live`, and `/health/ready` handler behavior with safe dependency mocks
- upload service rejection for path traversal, dangerous extensions, and oversize files
- valid image upload persistence with UUID filenames
- minimal WeasyPrint PDF rendering with a `%PDF` header

Protected-route end-to-end auth remains covered by manual UAT/smoke flows unless dedicated DB/auth fixtures are added later.

## Upload Security

Production upload defaults allow only JPEG, PNG, and WebP files up to 5 MB. The backend checks extension, declared MIME type, detected MIME type, path traversal, final resolved path, and writes UUID-based filenames. nginx sets `client_max_body_size 5M`, disables directory listing for `/uploads/`, and sends `X-Content-Type-Options: nosniff`.

Known upload limitations remain: uploaded files are publicly reachable by URL, malware scanning is not implemented, object storage is not configured, and per-tenant quotas/lifecycle cleanup are not implemented.

## nginx Security Headers

HTTP local production mode includes:

- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=(self)` so the same-origin POS
  scanner can request camera access while embedded and cross-origin pages remain blocked
- `Content-Security-Policy` restricting scripts to same-origin, blocking framing and objects, and limiting
  API/WebSocket/image/font connections to the reviewed application requirements

HSTS is intentionally present only in the HTTPS template. Do not enable HSTS on local HTTP mode.
The CSP keeps `'unsafe-inline'` for styles because the current component stack emits inline styles; scripts
do not allow inline execution. Re-test CSP behavior during visual UAT whenever frontend integrations change.

## Secrets Policy

Never commit:

- `.env.production` or real `.env.*` files
- registry credentials or tokens
- TLS certificates or private keys
- database dumps, SQL exports, backup archives, or generated release manifests
- real customer uploads or logs

Run the repository safety scans from [git-ci.md](./git-ci.md) before first commit and before release.

## Go-Live Blockers

Resolve or formally accept these before internet-facing production go-live:

- Confirm backend `pip-audit` remains clean in CI or the production build environment
- Run `./scripts/run-backend-regression.sh` before launch and after dependency upgrades
- Have the security owner formally accept the React Router RSC-mode advisory as non-reachable for the
  static `BrowserRouter` application, or complete and test the broader React 19/React Router 8 migration
- Formally accept the Vite/esbuild dev-server findings for the build-only toolchain, or upgrade Vite in a focused frontend tooling PR
- Confirm `ENABLE_API_DOCS=false` in production and verify `/api/docs` and `/api/openapi.json` return 404
- Complete visual browser/device UAT with the production CSP enabled
- Decide whether to clean up WeasyPrint/fontconfig cache warnings before launch or accept them as non-blocking while PDF rendering works
- Define the operational owner for monthly dependency and base-image updates

## Accepted Risks

Short-term acceptable only with operator sign-off:

- React Router RSC-mode finding is outside the static CSR execution path; production has no React Router server runtime or Actions
- Vite/esbuild findings affect the dev/build path; production serves static files from nginx
- WeasyPrint currently renders PDFs but emits fontconfig cache warnings in the non-root backend container
- Registry and deployment scripts do not store credentials and rely on host-level `docker login`
- Uploads are image-restricted but not malware-scanned
- Centralized vulnerability monitoring is not implemented yet

## Recurring Audit Schedule

- Before each release: `npm audit --audit-level=moderate`, backend dependency audit, Docker build, Compose config validation
- Monthly: review base-image updates and rebuild production images
- Quarterly: review nginx headers, CORS origins, public API docs exposure, upload policy, and secret rotation
- After any critical advisory: patch and deploy out of cycle
