# Phase 5 Production Readiness Workbook

This workbook separates evidence that can be prepared without production access from decisions and tests that require the real devices or accountable owners. Completing an automated rehearsal does not activate production or approve Phase 6.

```text
physical_device_uat: pending
server_migration_plan: post_cutover_observation; UAT hostname active
uat_tenant_auto_login: temporarily enabled 2026-09-10; disable before security UAT/sign-off
source_server_inventory: read_only_complete
target_server_inventory: read_only_complete
isolated_target_restore: core restore/migration/smoke passed; auth and device flows pending
server_cutover: complete on tailnet HTTPS; source retained for rollback
security_owner_decision: pending
operator_owner_signoff: pending
platform_owner_completion_signoff: pending
production_activated: false
phase6_started: false
```

## Release candidate

```text
draft_pr: https://github.com/chaiyanutaiagent/restaurant/pull/2
release_commit:
release_tag:
artifact_manifest: /private/tmp/restaurant-p5-artifacts/p5-production-readiness-05-20260801T162909Z/manifest.txt
reviewed_at_utc:
reviewed_by:
```

The release candidate remains a Draft PR until automated checks pass and reviewers have reviewed the diff. Record immutable commit and artifact references before approval; do not use a moving branch name as final evidence.

## Prepared non-device evidence

- Isolated clean-volume migration and application startup.
- Backend regression and the complete QR menu to kitchen, payment, stock, accounting, outbox, and central-report API chain.
- Standalone Chromium mobile/tablet flow with screenshots and checks for page errors, console errors, HTTP 5xx responses, and horizontal overflow.
- One hundred offline-origin orders synchronized in two batches, including lost-acknowledgement replay and database-level idempotency checks.
- Frontend type-check/build, shell syntax validation, documentation validation, and repository safety checks.
- Fresh backend and frontend dependency audits, with failure on any unreviewed package/advisory or critical finding.
- Draft operator drill, incident scenarios, device test matrix, and security risk-decision form.

Run the isolated gate with a non-production password and an isolated Compose project:

```sh
P5_READINESS_ADMIN_PASSWORD='use-a-unique-test-secret' \
  ./scripts/rehearse-phase5-readiness.sh --yes
```

The script is destructive only to Compose projects whose name begins with `restaurant-p5-uat-readiness`. It must never be pointed at production volumes.

## Temporary single-tester UAT access

The public UAT stack may temporarily set `UAT_AUTH_BYPASS_ENABLED=true` together with an explicit
UAT Company ID and active tenant-superuser username. The backend rejects this mode unless
`ENVIRONMENT=development` and `SAAS_PUBLIC_BASE_URL` is HTTPS on a hostname beginning with `uat-`.
The browser then obtains a normal, audited tenant session automatically when it reaches a tenant
login page. Production and Platform Owner authentication are not bypassed, and device pairing
remains enabled. Set `UAT_AUTH_BYPASS_ENABLED=false` and recreate the UAT backend before formal
login, permission, pairing/revocation, security UAT, or owner sign-off.

## Production values to be supplied by owners

```text
production_base_url:
server_or_cluster:
dns_owner:
tls_owner:
secret_source:
release_operator:
database_backup_location:
backup_retention_days:
backup_rpo:
last_isolated_restore_artifact:
monitoring_destination:
alert_primary:
alert_secondary:
rollback_decision_owner:
business_uat_owner:
security_owner:
platform_owner:
```

Do not put passwords, tokens, private keys, database URLs, customer data, or backup contents in this workbook or Git.

## Owner-controlled gates

- [ ] Fill the production values above without exposing secrets.
- [ ] Review the Draft PR and confirm its commit matches the release candidate.
- [ ] Re-run dependency audits and record the security-owner decision in [security-risk-acceptance.md](./security-risk-acceptance.md).
- [ ] Complete [device-uat-checklist.md](./device-uat-checklist.md) on the real counter, kitchen, and pickup devices.
- [ ] Complete the operator tabletop and command walk-through in [operator-training-drill.md](./operator-training-drill.md).
- [ ] Confirm the latest backup and isolated restore evidence meets the declared RPO and retention policy.
- [ ] Verify DNS, TLS, environment, monitoring destination, alert routing, and rollback ownership.
- [ ] Review [go-live-checklist.md](./go-live-checklist.md), [operator-handoff.md](./operator-handoff.md), [incident-quick-guide.md](./incident-quick-guide.md), and [sign-off.md](./sign-off.md).
- [ ] Obtain security, operator/business, and Platform Owner approvals.

## Next work queue

Resume with scope `P5-PHYSICAL-UAT-SIGNOFF-06`. The scope remains part of Restaurant Phase 5; the `06` suffix is only the next work-record sequence and does not mean Takeaway Phase 6 has started.

The owner requested server-migration planning before Tablet UAT on 9 August 2026.
Follow [server-migration-plan.md](./server-migration-plan.md) first. Planning and
an isolated target rehearsal are authorized; a live cutover, final hostname switch,
or source-server shutdown still requires a separate explicit decision.

| Order | Trigger | Work | Required evidence | Owner/status |
| --- | --- | --- | --- | --- |
| 1 | Before target-host changes | Inventory the current Restaurant source host, target host, database runtime modes, backups, RPO/downtime, and accountable owners without recording secrets | Reviewed non-secret inventory and identified authoritative databases | `in_progress` |
| 2 | Inventory reviewed | Rehearse backup transfer and restore only in an isolated target Compose project; verify checksums, migration heads, uploads, smoke, and reconciliation | Target restore evidence with unchanged source fingerprint | Pending |
| 3 | Target rehearsal passes | Correct and verify the camera permission policy, create the UAT-only Tunnel, and expose only the approved UAT hostname | Healthy UAT route, expected response headers, external health/smoke, camera preflight | Route and external smoke passed 2026-09-10; physical iPad camera permission pending |
| 4 | Target hardware arrives | Run [device-uat-checklist.md](./device-uat-checklist.md) on counter, kitchen, pickup display, camera, printer, and actual network | Dine-in/takeaway, pairing/revocation, restart, offline/lost-ack, printer, and reconciliation evidence | `waiting_for_hardware` |
| 5 | Any migration/UAT item fails | Fix only the approved failure scope, re-run regression/readiness gates, and repeat affected restore/device cases | Linked defect, immutable fix commit, green CI, and affected retest | Conditional |
| 6 | Device release candidate is stable | Re-run dependency audits against the exact commit and complete [security-risk-acceptance.md](./security-risk-acceptance.md) | Security-owner accept/mitigate/block decision | Pending |
| 7 | UAT and security decision pass | Run [operator-training-drill.md](./operator-training-drill.md), finish production/go-live checklist, and confirm backup/restore, monitoring, TLS, and rollback ownership | Operator/business sign-off and completed production checklist | Pending |
| 8 | All prior rows pass | Obtain Platform Owner Restaurant completion approval and update the Restaurant Completion Gate | Approved sign-off record tied to the release commit | Pending |
| 9 | Completion approval exists | Ask for separate explicit decisions for server cutover/final hostname, PR ready/merge, production activation, or Takeaway Phase 6 | Recorded owner instruction and change scope | Blocked until approval |

When resuming, first confirm the hardware inventory, target browser/app versions, printer connection type, network profile, UAT environment, and accountable people. Do not store credentials or pairing secrets in Git.

## Stop conditions

Stop the release if any required automated gate fails, a production value is unknown, a security risk is blocked, device UAT fails, reconciliation differs, backup/restore evidence is stale, or an accountable approver is unavailable. Do not deploy, migrate a live database, create live Platform Owner credentials, or begin Phase 6 from this workbook alone.
