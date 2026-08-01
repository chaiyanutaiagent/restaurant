# Phase 5 Production Readiness Workbook

This workbook separates evidence that can be prepared without production access from decisions and tests that require the real devices or accountable owners. Completing an automated rehearsal does not activate production or approve Phase 6.

```text
physical_device_uat: pending
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

## Stop conditions

Stop the release if any required automated gate fails, a production value is unknown, a security risk is blocked, device UAT fails, reconciliation differs, backup/restore evidence is stale, or an accountable approver is unavailable. Do not deploy, migrate a live database, create live Platform Owner credentials, or begin Phase 6 from this workbook alone.
