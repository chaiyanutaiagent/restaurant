# Takeaway Store hardening audit

Audit date: 2026-09-30, Asia/Bangkok. Audience: CTO and QA.

The live baseline remains UAT `1.1.0-uat.7` / version code `10106`, from release
`25fea8a36b9fa0a68774922f7fc742b4eef37b3d`. This candidate branches from
`c5bcb30f83bd1ef3ec4fae4bd6329823186c2bbe` on
`codex/takeaway-store-production-guards`. Candidate changes have NOT been deployed,
merged, or published as an APK. Production approval is not implied.

## Read only server evidence

Host: `behappyaiagent@100.66.192.56` (`mainserver`). Compose project:
`restaurant-pos-uat-drill`. Public artifact check timestamp: `2026-09-30T05:01:28Z`.

| Check | Observed result |
| --- | --- |
| Backend container | `b03c77af4485`, healthy, restart count 0 |
| Backend image | `restaurant-pos-backend:uat-product-catalog-25fea8a` |
| Backend image digest | `088dfcf76b8e734366dff9c6523f93d1246725ac2a2aef4bbcce611e8c879071` |
| Backend start | `2026-09-30T03:18:45.63267005Z` |
| Frontend container | `980b1c536d84`, running, restart count 0 |
| Frontend image | `restaurant-pos-frontend:uat-product-catalog-25fea8a` |
| Frontend image digest | `c964f2fcfda16afb7fce68830c7130d7f1f9780c638d695bfac7683a6aab3a95` |
| Frontend start | `2026-09-30T03:18:45.91642421Z` |
| Release directory | `/home/behappyaiagent/restaurant-uat-releases/25fea8a` |
| Ready endpoint | HTTP 200, `status=ok` |
| Migration | Read-only transaction in `takeaway_ops_db`: `p6takeaway0009` |
| Catalog columns | `description`, `image_url`, `sort_order`, `is_featured` all present |
| Catalog image data | 51 rows in total, 0 with a nonempty image URL; real product-image delivery cannot be certified with this dataset |
| Public roots | `uat-pos`, `uat-app`, `uat-restaurant`, `uat-retail`, `uat-takeaway` all HTTP 200 |

The health response still reports application version `uat-mobile-store-60fd4d9`.
That label is stale relative to the image tag; it is not evidence of deployed
source revision. Release identification must use image digests and the signed
manifest until a separately approved deployment corrects the version setting.

### Production observation and limits

No Production mutation, migration, login, or deployment was performed.
Read-only Docker metadata showed:

| Component | Container | Image | Started UTC |
| --- | --- | --- | --- |
| Backend | `19cb60909631` | `restaurant-pos-backend:auth-a0fdccf` | `2026-09-28T10:46:59.374019638Z` |
| Frontend | `55b5fadf98d6` | `restaurant-pos-frontend:prod-ea6de47` | `2026-09-28T10:46:59.35576Z` |

Both restart counts were 0 and their starts predate this UAT release.
Selected Production environment fields: `ENVIRONMENT=production`,
`UAT_AUTH_BYPASS_ENABLED=false`; `QA_ACCESS_MODE_ENABLED` and
`UAT_SUPERADMIN_ALL_LOGINS_ENABLED` unset. The candidate's defaults for the latter
flags are false. This is metadata evidence, not a claim that all historic
Production files/data were unchanged: no pre-deployment Production database or
filesystem snapshot was available for a full comparison.

UAT currently has `environment=development`, `uat_auth_bypass_enabled=true`,
`qa_access_mode_enabled=false`, `uat_superadmin_all_logins_enabled=true` and
`saas_public_base_url=https://uat-pos.foodchainservice.com`. These are existing
test settings, not permission to enable them in Production. No values changed.

## Published artifacts and backup verification

Both manifests were downloaded from the public UAT URL and verified using the
existing local UAT build's pinned Ed25519 public key. Key PEM SHA-256:
`7eae37031542191cfe44368e635139496521dc314c8f018b15f4868d67e2efde`.
No private signing key was read or changed.

| Artifact | Bytes | SHA-256 | Result |
| --- | ---: | --- | --- |
| UAT 7 APK | 4460932 | `a9e9c500105fce3db9cd42ed0f1cf64a9df216a0d08a446e14a8899e1e6c8c6f` | Hash and manifest signature match |
| UAT 6 APK | 4434949 | `b125db2e68db4c48fd9c7e1b752310ffa85bd58729d41ddb7773b73bd8e2eb7a` | Hash and manifest signature match |

`latest.json`: code/minimum `10106`, rollback `10105`.
`latest-uat.6.json`: code/minimum `10105`, rollback `10104`.
Both satisfy the candidate's stricter release policy. Android `apksigner verify`
on the downloaded UAT 7 APK passed v1/v2. Certificate SHA-256:
`acfe7c0638c1375ce6c041d53f99edac9467dfec64f7297ee07f3436704015b5`.
It is an **Android Debug** signer, not an approved Production signing identity.
The tool reported standard v1 META-INF unsigned-entry warnings; v2 verification
and the whole-file manifest checksum passed.

Backup directory:
`/home/behappyaiagent/restaurant-uat-deploy-backups/product-catalog-before-4ea36e9-20260929T152849Z`.

All seven entries in `SHA256SUMS` passed: `legacy.dump`, `platform.dump`,
`restaurant.dump`, `retail.dump`, `takeaway.dump`, `redis.tar.gz`, `uploads.tar.gz`.
`pg_restore --list` successfully read all five database dumps. The captured
listing lengths were respectively 1803, 357, 1242, 457 and 189 lines; these are
archive listing lengths, NOT database row counts. Environment/compose files are
present, but the seven-entry checksum file does not certify their contents.
No backup contents or secrets were copied to the Mac.

Rollback image IDs still exist on the server:

- Backend `uat-superadmin-fce44bd`: `823f246e6eb00c7b7c0349abc3c05170fcbc19f2f448451149cea17da8e80e60`.
- Frontend `uat-store-updater-2a9d199`: `963507cc83177b3e98adc53a927bc32f03ecb791f9e9421b7f158b24756b7b05`.

Backup integrity and readability are verified; a full isolated restore rehearsal,
restored row reconciliation and encrypted off-host backup remain unverified.
The saved `uploads.tar.gz` is only 91 bytes: confirm whether an empty upload tree
was expected before treating it as evidence of image recovery.

## Candidate changes

- Store UAT superadmin runtime checks now reject HTTP, malformed base URLs and
  empty configured usernames, alongside the existing environment/company/user gate.
- Store session checks bind token subject to returned employee; onboarding rejects
  a login response for a different business code.
- A shared browser/CLI release policy binds package, channel and exact download
  host, validates version/rollback ranges, and rejects unexpected tenant fields.
- Installation rechecks the signed manifest and current installed package/version;
  mutable UI flags alone cannot authorize an update. Manifest/APK redirects are denied.
- Native certificate checks fail closed when signer data is absent, including
  legacy Android signature handling; Production APKs cannot use UAT download hosts.

## Automated verification

| Gate | Result |
| --- | --- |
| Backend unittest discovery | 604 run, 603 passed, 1 skipped; no failures |
| Node release policy and CLI integration | 3 passed, including signed invalid manifests and tampering |
| TypeScript | `tsc --noEmit -p frontend/tsconfig.json` passed |
| Store browser tests | 13 cases passed across the initial run and a targeted timeout rerun; see detail below |
| Dedicated Store build and bundle boundary | Passed; 6 compiled files checked for prohibited routes, auto-login and default tenant |
| Android unit tests | 5 passed, including 4 new URL and certificate policy tests |
| Android lint | Passed with warnings; no fatal/error findings |

Backend command (local container, read-only candidate source):

```sh
docker compose -f /Users/user/Projects/restaurant/docker-compose.yml run --rm --no-deps \
  -e PYTHONPATH=/review/backend -e UPLOAD_DIR=/tmp/store-test-uploads \
  -v /private/tmp/restaurant-store-hardening-20260930:/review:ro \
  -w /review/backend backend python -B -m unittest discover -s tests -p 'test_*.py'
```

The skipped case needs `RETAIL_DATABASE_URL`; no Retail database was started or
changed. The first attempt failed because import-time upload-directory creation
targeted a read-only source mount; rerunning with a container-local scratch upload
directory resolved this. A missing field in a newly added test fixture was also
corrected before the passing run. Existing short HMAC test-key/deprecation
warnings and the intentionally mocked webhook network-failure log are not
Production credential tests.

Browser/native commands, run from `frontend` with a local disposable public-key
fixture and the UAT-only build configuration:

```sh
npx playwright test --config=playwright.mobile-store.config.ts
npm run build:android:uat
JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home \
ANDROID_HOME=/opt/homebrew/share/android-commandlinetools \
./android/gradlew -p android testDebugUnitTest lintDebug --console=plain
```

The initial frontend attempts were stopped by the existing build guard because
the new worktree had no release-channel configuration. A test-only public key was
generated locally; no real signing secret changed. The generated assets are not
approved for distribution. The build still warns about a large JS chunk.

Browser initial run: 12 passed and the multi-navigation forbidden-URL case hit
the 30-second timeout during parallel builds. Only that case was repeated with
`--grep 'manual forbidden URLs' --timeout=120000`, and passed. No assertion or
application code was weakened to obtain that result. The browser suite uses
mocked APIs; it is not a live transaction or physical-device acceptance run.

The Node gate is reproducible with
`node --test scripts/tests/takeaway-store-release-policy.test.mjs`.

Native reports remain locally at `frontend/android/app/build/test-results/` and
`frontend/android/app/build/reports/lint-results-debug.html`; generated artifacts
and the dependency symlink are excluded from the commit. Tests do not prove
physical installation, printer behavior or concurrent database stock locking.

## Remaining gates

- UAT deployment of this candidate needs separate approval; published UAT 7 does
  not contain these new fixes.
- Physical tests remain pending, including printer, cash drawer, payment, scanner,
  offline recovery and APK installation. No human acceptance is claimed.
- Production stays blocked by test access, release signing, physical acceptance,
  backup recovery evidence and monitoring ownership. See the companion runbook
  and multi-company architecture review.
