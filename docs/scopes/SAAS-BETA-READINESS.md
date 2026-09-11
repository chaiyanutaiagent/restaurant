# SaaS Beta Readiness Handoff

## Decision

The authorized SaaS preparation work in Scopes 01-08 is complete and has passed the local
beta evidence gate. This result means **beta candidate**, not public-launch approval and not
production readiness certification.

```text
saas_preparation_scopes_01_08: complete
local_beta_evidence_gate: passed
public_launch_approved: false
production_activated: false
restaurant_physical_uat: parked_waiting_for_hardware
takeaway_phase6_started: false
retail_phase7_started: false
```

The scope authority and release boundaries remain controlled by
[`SAAS-PREP-WORK-PLAN.md`](./SAAS-PREP-WORK-PLAN.md).

## Tested baseline

- Branch: `agent/phase5-completion-gate`
- Scope 08 input commit: `a24f0e5` (`feat: add tenant-approved SaaS privacy support`)
- Scope 08 behavior changes: none; this gate adds evidence automation, test-harness fixes,
  and this report only.
- Live local migration heads stayed unchanged: legacy `6b7c8d9e0f12`, Platform
  `p1platform0003`, Restaurant `p1restaurant0003`.
- Isolated beta target heads: legacy `p11privacy0013`, Platform `p11platform0015`,
  Restaurant `p1restaurant0003`.
- Scope 08 added no Alembic revision and applied no migration to a source or production
  database.

## Gate results

| Area | Result | Evidence |
| --- | --- | --- |
| Combined migrations | Passed | Both affected clones upgraded, downgraded one revision, and re-upgraded; Restaurant clone stayed at its release head |
| Full backend regression | Passed | 223 tests |
| Python dependency consistency | Passed | `python -m pip check` reported no broken requirements |
| Static SaaS boundary scan | Passed | Secret markers, impersonation routes, provider-specific charging, and destructive privacy execution remained outside the authorized boundary |
| Latest-schema API smoke | Passed | Platform operations plus two-Tenant/two-operator privacy/support authorization and isolation |
| Bounded local load probe | Passed | 120 requests, concurrency 10, zero errors, p50 62.18 ms, p95 238.07 ms, max 311.06 ms, 114.43 requests/second |
| Frontend clean install | Passed | `npm ci --no-audit --prefer-offline`; lockfile remained unchanged |
| Frontend type/build | Passed | TypeScript no-emit check and Vite production build |
| Browser regression | Passed | 10/10 Platform, public account, billing, privacy, and support flows |
| Offline npm advisory cache | Passed with limitation | Zero locally cached findings for production dependencies; no claim of current online coverage |
| Backup and restore | Passed | Three-boundary dump, matching content checksum, isolated restore, cleanup, measured local RTO 6 seconds |
| Source protection | Passed | All three live local source fingerprints were unchanged |

The load result is a bounded local regression signal for aggregate Platform endpoints. It
is not an unlimited-scale claim, capacity plan, or production SLA.

## Scope evidence chain

The final gate verified that the latest local manifests for Scopes 02-07 were present and
then generated the Scope 08 manifest. Scope 01 is represented by its focused tests and
commit because its dashboard-only gate predates the manifest convention.

| Scope | Commit | Evidence |
| --- | --- | --- |
| Plan | `01dcdae` | SaaS preparation scope-control plan |
| 01 Dashboard | `90abe31` | 15 backend tests, frontend build/type check, 3 browser tests |
| 02 Platform auth | `f2ee07f` | `/private/tmp/restaurant-saas-artifacts/saas-platform-auth-02-20260803T064239Z/manifest.txt` |
| 03 Tenant usage | `3cb31e0` | `/private/tmp/restaurant-saas-artifacts/saas-tenant-usage-03-20260803T065817Z/manifest.txt` |
| 04 Membership | `23c1d1d` | `/private/tmp/restaurant-saas-artifacts/saas-membership-04-20260803T072035Z/manifest.txt` |
| 05 Operations | `44ca325` | `/private/tmp/restaurant-saas-artifacts/saas-operations-05-20260803T073547Z/manifest.txt` |
| 06 Billing boundary | `b53860d` | `/private/tmp/restaurant-saas-artifacts/saas-billing-06-20260803T075734Z/manifest.txt` |
| 07 Privacy/support | `a24f0e5` | `/private/tmp/restaurant-saas-artifacts/saas-privacy-support-07-20260803T081908Z/manifest.txt` |
| 08 Combined beta gate | Scope 08 commit | `/private/tmp/restaurant-saas-artifacts/saas-beta-readiness-08-20260803T083225Z/manifest.txt` |

Artifacts under `/private/tmp` are local evidence and are intentionally not committed
because they can include database dumps. The Markdown plan and this handoff are the durable
repository record.

## Known warnings and follow-ups

1. Test configuration emits an HMAC key-length warning because its local JWT key is 30
   bytes. A production environment must supply a strong secret of at least 32 bytes and
   pass the existing production-configuration guard before deployment.
2. The current Starlette test client emits an `httpx` deprecation warning. This does not
   fail the tests, but the compatible framework/client upgrade should be a separately
   scoped dependency-maintenance change.
3. The production bundle is approximately 2.36 MB before gzip and Vite reports a chunk over
   500 kB. Code splitting is a future performance Scope, not a correctness failure here.
4. `npm audit --offline` reported no cached production findings. A current online registry
   advisory lookup was not run because it would disclose dependency/lock metadata and needs
   explicit owner authorization. It must be recorded before a public-launch go/no-go.
5. The billing implementation is provider-neutral and live collection is deliberately
   disabled. Provider selection, commercial policy, keys, webhooks, reconciliation, tax
   treatment, and live charging require a future approved Scope.
6. Privacy and retention features are controlled workflows, not legal advice or a legal
   compliance certification. Retention decisions do not automatically delete or anonymize
   Tenant data.

## Public-launch blockers

Public launch remains blocked until all of the following are separately approved and
completed:

1. Restaurant `P5-PHYSICAL-UAT-SIGNOFF-06` on real counter, kitchen, pickup, camera,
   printer, and network hardware.
2. A production deployment Scope covering secrets, infrastructure, migration rehearsal
   against production-like copies, monitoring/alert delivery, rollback, and operator runbook.
3. Billing provider and commercial-policy selection if paid self-service launch is required.
4. A current authorized online dependency advisory check and disposition of any result.
5. Owner go/no-go using both the SaaS beta evidence and Restaurant hardware-UAT evidence.

No work in this handoff authorizes production deployment, Takeaway Phase 6, or Retail Phase 7.

## Re-run

```bash
bash scripts/rehearse-saas-beta-readiness.sh --yes
cd frontend
npm ci --no-audit --prefer-offline
npm audit --offline --omit=dev --audit-level=high
npm run type-check
npm run build
npm run e2e:platform
```
