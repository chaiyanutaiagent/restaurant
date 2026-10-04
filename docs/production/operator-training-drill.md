# Phase 5 Operator Training and Incident Drill

Run this 60–90 minute session before go-live with the actual release operator, business/operator owner, incident lead, and backup/rollback decision owner. The first session should use an isolated or staging environment; no destructive restore or migration rollback may target live production during training.

## Attendance and evidence

```text
date_utc:
release_commit:
environment:
facilitator:
release_operator:
business_operator:
incident_lead:
backup_restore_owner:
rollback_decision_owner:
security_contact:
evidence_location:
result: pending
```

## Suggested agenda

1. Ten minutes: ownership, escalation path, stop conditions, and secret-handling rules.
2. Fifteen minutes: health, service status, logs, request IDs, disk, TLS, and backup freshness.
3. Fifteen minutes: safe release, smoke test, migration status, and app-only rollback walkthrough.
4. Twenty to thirty minutes: two or more incident tabletop scenarios below.
5. Ten minutes: daily/weekly/monthly routine, open questions, actions, and sign-off decision.

## Safe command walk-through

Use the real production environment path only when authorized. Never paste secret values into chat, tickets, screenshots, or shell history.

```sh
./scripts/check-production-env.sh .env.production
./scripts/check-production-status.sh
./scripts/smoke-production.sh .env.production
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 backend nginx postgres redis
```

The operator must be able to locate the applicable deploy, rollback, backup/restore, observability, TLS, incident, and sign-off documents without guessing.

## Routine ownership

- Daily: health/readiness, failed alerts, disk headroom, backup recency, certificate warnings, and unresolved incident handoff.
- Weekly: sample restore metadata/checksum, review error trends and device revocations, and confirm escalation contacts.
- Monthly: isolated restore drill according to policy, dependency/base-image review, access review, and retention cleanup verification.
- Per release: immutable commit/tag, environment validation, backup, migration plan, smoke/UAT, reconciliation, risk decision, and rollback owner.

## Tabletop scenarios

For each selected scenario, record detection, first safe check, owner, customer impact, containment, recovery, rollback/restore decision point, evidence, and communication.

- PostgreSQL unavailable or `/health/ready` reports database failure.
- Redis unavailable while the application process remains live.
- Disk or uploads volume nearly full.
- Latest backup missing, stale, checksum-invalid, or outside the stated RPO.
- Deployment or migration fails before readiness becomes healthy.
- Operator receives no response after payment/order submission and is tempted to resubmit.
- TLS certificate expiry/renewal failure or unexpected HTTP exposure.
- Device credential is lost, stolen, mis-scoped, or must be revoked urgently.
- Printer is offline or out of paper during a busy service period.
- Central report does not reconcile with source order/payment/stock records.

## Pass criteria

- [ ] Named owners can find the authoritative runbook and escalation contact.
- [ ] The operator distinguishes liveness from readiness and can correlate a request ID without exposing credentials.
- [ ] The operator states when to stop, when app-only rollback is safe, and when data restore requires explicit destructive approval.
- [ ] The backup owner identifies the latest valid isolated restore evidence and its RPO/retention context.
- [ ] The team explains why retry/idempotency protects a lost acknowledgement and still verifies reconciliation.
- [ ] Open risks and follow-up actions have an owner and due date.
- [ ] Business/operator owner records a pass decision; no blank field is treated as approval.

```text
scenarios_run:
observations:
follow_up_owner_and_due_date:
operator_owner_signoff: pending
```
