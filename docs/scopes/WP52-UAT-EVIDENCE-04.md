# WP52 UAT Evidence — Restaurant Exceptions and Receipt Center

Date: 2026-09-22
Environment: UAT only
Decision: **PASS — engineering, API, paired-Counter visual acceptance and rollback passed**

## Release identity

| Item | Evidence |
|---|---|
| Frontend feature commit | `44a1b36` (`feat: compose WP52 restaurant exception UX`) |
| Offline-boundary correction | `d12b327` (`fix: require authorized offline order sync`) |
| Final harness commit | `e4e3ad9` (`test: align refund smoke with shift blockers`) |
| Pairing browser-compatibility commit | `0d0e021` (`fix: make device pairing browser compatible`) |
| Final immutable release | `/home/behappyaiagent/restaurant-uat-releases/0d0e021` |
| Final archive SHA256 | `36c04e77051079e7bba01fb55e2f4325c4c4f294f4b99f8d83b50e948af51310` |
| Backend image | `restaurant-pos-backend:wp52-e4e3ad9` |
| Backend image ID | `sha256:309d824b50079a5ff2f8d4c14d27910c6768d688bfb0211a5b50ce954e9ee885` |
| Frontend image | `restaurant-pos-frontend:wp52-0d0e021` |
| Frontend image ID | `sha256:00711916e359f4afb65dd94ec8554f525182f2366b3131a9ae1f3cda2ef80994` |
| UAT stack | `restaurant-pos-uat-drill` |

## Local engineering evidence

- Frontend TypeScript check: PASS.
- Frontend production/PWA build: PASS; existing large-chunk warning only.
- Pairing-dialog regression: PASS — 6 focused source-contract checks, including no browser `prompt`/`confirm` dependency.
- Focused WP regression: PASS — 60 tests.
- Full backend regression: PASS — 460 tests, 1 skipped.
- Git whitespace validation: PASS.

## UAT defect detection and correction

The first WP43 smoke run found that the legacy online WAP endpoint accepted `is_offline=true` after the
WP47 authorized sync path was introduced. Server pricing still remained authoritative, but the request
could bypass the signed Offline Sync envelope. Commit `d12b327` now rejects this flag on both direct WAP
and Brand Store online endpoints with the existing machine-readable `stale_price` response. The signed
`/orders/sync` routes remain unchanged. The full WP43 smoke then passed.

The first WP46 rerun reached the correct WP51 `shift_close_blocked` envelope containing the
`refunds_pending` blocker, while its older harness expected the blocker at the top level. Commit
`e4e3ad9` aligned the assertion without changing Refund behavior. The rerun passed.

## API and authority evidence

| Contract | Result |
|---|---|
| WP43 price/discount/override | PASS — authority, tamper resistance, approval, replay, version and offline fail-closed checks |
| WP45 cancellation/Waste/Audit | PASS — stage, maker-checker, KDS acknowledgment, Waste and immutable audit checks |
| WP46 provider refund/tax | PASS — quote, remaining balance, cash/provider recovery, concurrency, sandbox webhook and synthetic non-fiscal tax checks |

No live provider call or real tax/Credit Note submission occurred.

## Formal paired-Counter browser UAT

Normal `uat.branch-manager` authentication was reused; authentication bypass stayed disabled and no
credential was written to Git or evidence.

| Check | Result |
|---|---|
| Current WP52 asset | PASS — POS showed `ศูนย์บิล`, current signed menu and Server status |
| Counter pairing | PASS — rotated the UAT-only PIN for `UI-DEVICE-01`, paired the current browser through the normal one-time flow and retained the signed Staff session |
| Staff shift | PASS — paired Counter accepted the existing open Staff shift `FB20260922000741` with the correct Branch and warehouse |
| Discount workspace | PASS — amount/percent modes, quick percentages, before/discount/after totals, missing structured-reason disclosure and Server-authority copy |
| Receipt fixture | PASS — created UAT-only sale `SO20260922-0001` for one `น้ำเปล่า`, cash ฿15.00; receipt totals and VAT rendered correctly |
| Bill Center | PASS — current-shift refresh, order-number search, paid-status filter, detail, item/payment/refund summary and receipt entry point |
| Safe Void routing | PASS — settled cash disabled Void and directed the user to Refund; temporary UAT-only `authorized` state on `SO20260922-0002` enabled the Void form, then the fixture was restored to `unknown` without executing Void |
| Cancellation preview | PASS — pending order preview showed no Waste; completed-kitchen order preview showed bill impact, recipe Waste and KDS/Audit disclosure |
| Cancellation approval | PASS — after-kitchen cancellation opened bounded Manager maker-checker with action/reason summary; no cancellation was executed |
| Refund | PASS — Server quote returned gross/base/VAT and original cash allocation; Sandbox and non-fiscal boundaries were visible; Manager maker-checker opened without executing the refund |
| Desktop default viewport | PASS for POS, Bill Center, Void, Cancellation approval, Refund and receipt composition |
| iPad landscape 1024×768 | PASS for Bill Center and Refund composition; controls remained readable and touch-sized |

No pairing PIN, Manager PIN or staff credential was written to Git or evidence. The temporary viewport
override was reset after the tablet check. The browser remains paired to the UAT-only Counter for the
authorized test environment.

## Runtime boundaries

| Setting | Final UAT value |
|---|---|
| Authentication bypass | `false` |
| Refund provider | `sandbox` |
| Synthetic UAT Credit Note | `true` — non-fiscal/not submitted only |
| Offline mode | `true` — pre-existing WP47 UAT allowlisted path |
| Company Kitchen writes | `false` |
| Company Distribution writes | `false` |

## Public health and rollback

- `/`, `/pos`, `/admin`, `/health` and `/health/ready`: HTTP 200.
- UAT nginx HTTP 5xx during the final 15-minute check after restore: 0.
- WP52 → WP51 backend/frontend rollback: PASS — 13 seconds; local proxy health passed.
- WP51 → WP52 restore: PASS — 12 seconds; local and public health passed.
- Final frontend-only `wp52-0d0e021` → `wp52-44a1b36` rollback: PASS — 1 second.
- Final frontend-only restore to `wp52-0d0e021`: PASS — 1 second; paired Counter and Staff session remained valid.
- PostgreSQL, Redis, nginx and Cloudflare Tunnel were not recreated during the corrected rehearsal.

## Production isolation

| Service | Image | Container ID |
|---|---|---|
| Backend | `restaurant-pos-backend:auth-a0fdccf` | `f6e08435721a` |
| Frontend | `restaurant-pos-frontend:ui-e4200ca` | `857e0dbab1a2` |
| Nginx | `restaurant-pos-nginx:unified-d528512` | `aea97e7f90f7` |
| Cloudflared | `cloudflare/cloudflared:2026.7.0` | `ae6862f8a09f` |
| PostgreSQL | `postgres:15-alpine` | `3565e3fd72ad` |
| Redis | `redis:7-alpine` | `76658d7ad2fd` |

Production remained unchanged and is **NO-GO**.
