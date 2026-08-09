# Phase 5 Restaurant Server Migration Plan

This plan prepares a new Restaurant UAT host before physical-device testing. It is supporting
work under `P5-PHYSICAL-UAT-SIGNOFF-06`; it does not start Takeaway Phase 6 and does not
authorize a live migration or production cutover.

```text
planning_started_at: 2026-08-09
planning_status: cutover_approved; safe_route_preflight_blocked
source_server_inventory: read_only_complete
target_server_inventory: read_only_complete
isolated_restore_rehearsal: core_restore_migration_smoke_passed; auth_and_device_flows_pending
uat_hostname_activation: pending
physical_device_uat: pending
production_cutover_approved: true; owner instruction recorded 2026-08-09
production_activated: false
phase6_started: false
```

## Objective

Prepare and prove a replacement server that can host the current Restaurant release, its
durable data, uploads, and UAT hostname without changing the active server. The first public
route on the target should be a dedicated UAT hostname such as
`https://uat-pos.foodchainservice.com`. The final `foodchainservice.com` route remains a
separate owner-controlled production decision.

## Authorization boundary

The owner explicitly instructed the operator to switch to the replacement server on 9 August
2026. This authorizes the controlled cutover stages below, but does not waive backup,
reconciliation, route-preflight, or rollback requirements. The source must not be stopped until a
tested target route exists.

Authorized now:

- Read-only inventory of the source and target hosts.
- Target-host provisioning without a public production route.
- Backup verification and restore rehearsal into an isolated Compose project/database.
- UAT-only Cloudflare Tunnel, environment, smoke, and physical-device preparation.
- Documentation and fixes required to make the approved UAT path work.

Not authorized by this plan alone:

- Stopping the current server or blocking live users.
- Running a live migration, changing live migration heads, or restoring over a live database.
- Reusing or exposing production passwords, database URLs, Tunnel tokens, or private keys.
- Switching `foodchainservice.com`, deleting the source server, or erasing source backups.
- Deploying an unreviewed commit, creating live Platform Owner credentials, or starting Phase 6.
- Reading from, writing to, or changing the separate ERP-POS source repository.

## Repository baseline

- Repository: `chaiyanutaiagent/restaurant`; `origin` is the only permitted remote.
- Planning baseline: branch `agent/phase5-completion-gate`, commit `b2e36df`.
- Production-like application services are defined in `docker-compose.prod.yml`.
- The Cloudflare profile runs `cloudflared` beside Nginx and routes internally to
  `http://nginx:80`; the Tunnel token is read from `.secrets/cloudflare-tunnel-token`.
- PostgreSQL and uploads are durable systems of record. Redis contains operational
  cache/queue state and requires an explicit drain-or-restore decision.
- `scripts/backup-production.sh` backs up only `$POSTGRES_DB`, uploads, and Redis. If either
  `IDENTITY_DATABASE=platform_core` or `RESTAURANT_SERVICE_DATABASE=restaurant` is active,
  this single-database backup is not sufficient for a server migration.
- Baseline commit `b2e36df` sends `Permissions-Policy: camera=()` from the production Nginx
  variants, while the POS scanner uses `navigator.mediaDevices.getUserMedia`. The rehearsal patch
  changes this to `camera=(self)`; it still needs review/commit and physical Tablet verification.

The final release candidate must use an immutable reviewed commit, not the planning baseline
or a moving branch name.

## Non-secret inventory record

Record only labels and operational facts. Store command output and infrastructure evidence in
an approved private location outside Git. Never record passwords, tokens, private keys, full
database URLs, customer rows, pairing secrets, or backup contents here.

### Source host

```text
source_host_label: devserver
source_owner: pending
access_method_confirmed: true; private SSH endpoint retained outside Git
operating_system: Ubuntu 24.04.4 LTS
cpu_and_memory: 6 vCPU; 15 GiB RAM; 4 GiB swap
disk_total_free: 233 GiB root; 188 GiB free at inventory
docker_version: 29.6.2
docker_compose_version: 5.3.1
compose_project_name: restaurant-pos-prod
repository_commit: fb4e56a40409ee06d8cf7ac6db8165b419e2efe5
release_tag_or_manifest: initial-fb4e56a
public_hostname: temporary private-network HTTP pilot; endpoint retained outside Git
cloudflare_tunnel_label: none in the Restaurant Compose project
identity_database_mode: legacy; setting absent on the deployed baseline
restaurant_service_database_mode: legacy; setting absent on the deployed baseline
reference_projector_enabled: false/unset on the deployed baseline
postgres_database_count: one application database; two non-template databases including postgres
postgres_total_size: 15990119 bytes at inventory
uploads_size: 0 bytes at inventory
redis_queue_drain_owner: pending; Redis DBSIZE was 0 at inventory
latest_backup_label: restaurant-pos-prod-20260809T084430Z; fresh online migration backup
latest_restore_drill_label: restaurant-pos-uat-drill core restore/migration/smoke passed 2026-08-09
monitoring_destination: pending; local readiness returned HTTP 200
```

### Target host

```text
target_host_label: mainserver
target_owner:
operating_system: Ubuntu 24.04.4 LTS
cpu_and_memory: 6 vCPU; 15 GiB RAM; 4 GiB swap
disk_total_free: 98 GiB mounted root; 86 GiB free at inventory; underlying disk 238.5 GiB
docker_version: 29.7.2; overlayfs; cgroup v2
docker_compose_version: 5.4.0
compose_project_name: restaurant-pos-uat-drill
uat_hostname: uat-pos.foodchainservice.com
secret_source: target-only ignored .env.uat; production secret workflow pending
backup_staging_location: /home/behappyaiagent/restaurant-migration-staging (outside repository)
monitoring_destination: loopback health/status only; external alert destination pending
```

### Recovery objectives and owners

```text
maximum_approved_downtime:
backup_rpo:
migration_window:
migration_operator:
database_restore_owner:
cloudflare_route_owner:
rollback_decision_owner:
business_uat_owner:
security_owner:
platform_owner:
```

Unknown values remain blockers; do not guess them during cutover.

### Read-only inventory evidence — 2026-08-09

- Both hosts had synchronized NTP. The source used `Asia/Bangkok`; the target used `Etc/UTC`.
  Application records must continue to use explicit UTC timestamps and configured display zones.
- The source Restaurant stack was healthy but shared its host with unrelated Compose projects.
  Migration commands must always set the explicit Restaurant directory, Compose file, and project.
- The source repository was clean on `main` at `fb4e56a`, and its running images used the matching
  `initial-fb4e56a` tag. This is older than the current Phase 5 planning branch and requires an
  isolated upgrade rehearsal rather than an in-place source upgrade.
- Exact source counts were Company `1`, User `1`, Branch `2`, Brand `0`, Product `0`, Dining
  Session/Order `0`, Sale Order `0`, Payment `0`, and Stock Balance `0`.
- The source legacy database head was `1b2c3d4e5f60` across `101` user tables. The database was
  approximately 15.3 MiB, uploads were empty, and Redis contained no keys.
- The only source backup was created before the initial deployment on 30 July 2026. Its PostgreSQL
  dump was `868` bytes and is not accepted as a current migration backup or restore artifact.
- The target had no application containers, named volumes, or Restaurant repository. Only SSH and
  private-network listeners were present. Git could read the permitted Restaurant repository and
  resolve both `origin/main` and `agent/phase5-completion-gate`.
- Target free space is sufficient for the current small dataset and an isolated rehearsal, but
  growth/retention capacity must still be approved before production cutover.

### Online backup and isolated restore evidence — 2026-08-09

- A fresh online source backup was created at
  `/home/chaiyanut/restaurant/backups/server-migration/restaurant-pos-prod-20260809T084430Z`.
  The source services were not stopped.
- The backup contained a `465308`-byte PostgreSQL custom dump plus empty uploads and Redis
  artifacts. All three SHA-256 checksums matched after transfer to the target staging directory.
- The target was cloned clean on `agent/phase5-completion-gate` at `b2e36df`, with only the
  permitted `chaiyanutaiagent/restaurant` origin. Its ignored `.env.uat` uses new UAT secrets and
  `uat-pos.foodchainservice.com`; no source credential was copied into Git. The SMTP preflight and
  camera-policy patch was then applied locally for rehearsal, so the target checkout is now
  intentionally dirty and must not be treated as an immutable production release until that patch
  is reviewed, committed, and deployed from the permitted repository.
- Restore into the isolated `restaurant-pos-uat-drill` Compose project completed. PostgreSQL and
  Redis were healthy; migration head `1b2c3d4e5f60`, all recorded business row counts, empty
  uploads, and empty Redis state matched the source baseline before upgrade.
- The first Alembic upgrade attempt stopped before running migrations because the release's
  production settings require SMTP account-email delivery, while the UAT env did not yet define
  an SMTP transport. The target database therefore remained on its pre-upgrade head. The source
  database and running services were unchanged.
- The release preflight was tightened to require the production SaaS SMTP/HTTPS fields before
  migration or startup. Mailpit `v1.27.8` now provides an internal UAT-only SMTP catcher on the
  Compose network; its web interface binds to target loopback only. A synthetic `.invalid`
  recipient was captured successfully and no message was sent externally. Final production
  remains blocked on an approved SMTP provider/relay.
- Alembic then upgraded the restored copy from `1b2c3d4e5f60` to `p12route0014`. PostgreSQL grew
  from `101` to `123` public tables; Company `1`, User `1`, Branch `2`, and all recorded zero-count
  operational tables remained reconciled.
- The target backend, frontend, Nginx, PostgreSQL, and Redis started successfully with zero
  restarts. Production status and HTTP smoke passed on target loopback; `/health/ready` and `/`
  returned `200`, API docs returned `404`, and the response now permits same-origin camera access
  with `Permissions-Policy: ... camera=(self)`.
- Optional authenticated smoke was skipped because an approved UAT credential was not supplied.
  QR/order/payment/stock, printer, offline/retry, and Tablet checks remain part of physical UAT.
- A final read-only source check still showed clean commit `fb4e56a`, migration head
  `1b2c3d4e5f60`, all five Restaurant services running with zero restarts, and backend readiness
  `200`. No source migration, shutdown, route change, or production activation occurred.

## Stage 1 — Read-only source inventory

Run these only on the intended Restaurant host and keep their output outside Git:

```sh
uname -a
cat /etc/os-release
docker --version
docker compose version
df -h
free -h
git remote -v
git status --short --branch
git rev-parse HEAD
docker compose -f docker-compose.prod.yml ps --all
docker compose -f docker-compose.prod.yml config --services
```

Validate the environment without printing it:

```sh
./scripts/check-production-env.sh .env.production
```

Record the runtime modes by key name and approved value only. Do not print the whole env file.
Confirm the database list, migration heads, data size, upload volume, current backup location,
and latest successful restore evidence. Inventory commands must not create containers, start
services, run migrations, or write application records.

### Backup topology gate

Choose the backup path only after the runtime modes are known:

- Both modes `legacy`: the full production backup covers the authoritative PostgreSQL database,
  uploads, and Redis, subject to a successful isolated restore drill.
- Platform or Restaurant mode active: create and restore-verify full dumps of Legacy, Platform,
  and Restaurant databases in addition to uploads. Do not treat a single `$POSTGRES_DB` dump or
  a tenant JSON export as a complete host-migration backup.
- Any mode `unknown`, database names overlap unexpectedly, or migration heads differ from the
  reviewed release: stop and resolve the topology before copying data.

## Stage 2 — Prepare the isolated target

1. Provision the target host with supported Docker/Compose, adequate disk space, time sync,
   restricted SSH, firewall rules, and an encrypted backup staging location.
2. Clone only `https://github.com/chaiyanutaiagent/restaurant` and verify `origin`, the exact
   reviewed commit, clean status, and release manifest.
3. Create an ignored target environment such as `.env.uat`; use new UAT secrets and an isolated
   Compose project name. Do not copy source secrets into Git or chat.
4. Keep the target unreachable from the final production hostname. Use host loopback or a
   dedicated UAT hostname only.
5. Validate env, Compose config, image build/pull, Nginx config, disk capacity, and writable
   uploads before restoring any source copy.

Target readiness evidence:

```text
target_commit_verified:
target_env_validation:
target_compose_validation:
target_nginx_validation:
target_capacity_review:
target_secret_source_review:
```

## Stage 3 — Backup transfer and restore rehearsal

1. Create a fresh source backup without stopping the current server. Record its timestamp,
   size, checksums, database topology, and source commit.
2. Copy the encrypted backup to the target through an approved channel. Verify checksums after
   transfer; do not place backup files inside the repository.
3. Restore only into `COMPOSE_PROJECT_NAME=restaurant-pos-uat-drill` or another explicitly
   isolated target project. Confirm every target volume name before approving destructive restore.
4. If Redis contains queued work, decide whether to drain it on the source or restore it. Do not
   replay an unknown queue into the target.
5. Run the reviewed migration graph against the restored copy only after pre-migration backup
   evidence exists. Confirm Legacy, Platform, and Restaurant heads separately when those physical
   databases are present.
6. Compare row counts and business totals for Company, users/assignments, Brand/Branch, products,
   dining sessions/orders, payments, stock, accounting/outbox, and audit data. Verify upload
   count/checksum independently.
7. Run backend regression, frontend build, status, smoke, tenant isolation, login, QR-to-kitchen,
   payment, stock/accounting, and backup/restore checks.

The rehearsal passes only when the source remains unchanged and the target can be destroyed and
recreated from the same verified backup.

## Stage 4 — UAT hostname and Tablet preflight

1. Create a dedicated Tunnel such as `restaurant-uat`; never reuse the production Tunnel token.
2. Store the token on the target as `.secrets/cloudflare-tunnel-token` with restrictive file
   permissions. Do not run or publish a command containing the token.
3. Route `uat-pos.foodchainservice.com` to `http://nginx:80` only after target health checks pass.
4. Set matching `SERVER_NAME`, `PUBLIC_BASE_URL`, and exact `CORS_ORIGINS` in the ignored UAT env.
5. Correct the camera policy to allow the same origin, rebuild Nginx, verify the response header,
   and prove that the target Tablet can grant camera access.
6. Run external health/smoke tests and then complete `device-uat-checklist.md` with UAT-only users,
   orders, stock, and payment methods.

The UAT hostname is not evidence that production is activated. It must remain isolated from real
customer transactions unless a separate owner decision explicitly allows production UAT.

## Stage 5 — Cutover readiness gate

Before requesting a live migration window, all items must be complete:

- [ ] Source and target inventories are complete and reviewed.
- [ ] Exact release commit, image tags, and migration heads are immutable.
- [ ] Backup topology covers every authoritative database plus uploads.
- [ ] Backup transfer checksum and isolated restore rehearsal passed.
- [ ] RPO, maximum downtime, maintenance window, and owners are recorded.
- [ ] UAT hostname, automated smoke, Tablet/camera, printer, offline/retry, and reconciliation pass.
- [ ] Security decision, operator drill, monitoring, alert delivery, and rollback owner are ready.
- [ ] Source host remains available and unchanged for the rollback retention window.
- [ ] Platform Owner separately authorizes the actual cutover and final hostname switch.

## Stage 6 — Owner-approved cutover outline

This section is a plan, not current authorization.

1. Announce maintenance and block new writes at the approved time.
2. Drain or intentionally discard/recreate Redis operational work according to the recorded
   decision; verify no in-flight business transaction remains.
3. Create the final backup, record checksums and source migration heads, and keep the source
   application stopped/read-only.
4. Transfer and checksum the final backup, restore the isolated target volumes, and run only the
   reviewed migrations.
5. Start the target without the final public route. Run readiness, smoke, auth, QR/order/payment,
   stock/accounting, upload, and reconciliation checks.
6. Switch the final Cloudflare published application route to the dedicated production Tunnel.
   Do not run independent old and new application writers against separate databases.
7. Observe error rate, container restarts, database connections, queue state, orders/payments,
   and reconciliation during the agreed validation window.
8. Record go/no-go. Keep the source host and final pre-cutover backup intact until the rollback
   retention period expires.

## Rollback rules

### Before the target accepts writes

Stop the target, return the route to the source, verify source health, and reopen writes. Preserve
the failed target and logs for analysis.

### After the target accepts writes

Do not point users back to the old independent database automatically. Freeze writes on both
sides, quantify target-only transactions, and let the rollback owner choose a reviewed forward
fix, controlled reconciliation, or destructive restore. The acceptable data-loss window must not
exceed the approved RPO.

### Source retirement

Do not delete the source host, volumes, backups, Tunnel, or release artifacts during cutover.
Retirement needs a separate confirmation after the target has remained stable, backups have run,
and a target restore drill has passed. A practical retention window must be selected by the owner;
this plan does not assume one.

## Current blockers and next inputs

- Source and target access owners still need accountable names even though SSH access is confirmed.
- The target secret source, backup staging path, and monitoring destination are not assigned.
- Maximum downtime, RPO, maintenance window, and rollback owner are not assigned.
- Core restore, migration, non-auth smoke, and count reconciliation passed on the isolated target.
  Authenticated and business-flow smoke still need an approved UAT credential and test fixtures.
- Final production SMTP provider/relay settings are not assigned; the current Mailpit transport is
  UAT-only and must not be used as production email delivery.
- The Nginx camera policy was build/header verified but still needs actual Tablet permission UAT.
- UAT and production Cloudflare Tunnel tokens/routes have not been created on the target.
- The target Tailscale HTTPS route cannot be enabled by the SSH account until an administrator runs
  `sudo tailscale set --operator=behappyaiagent` (or performs the Serve command directly). The
  browser-controlled Cloudflare alternative is also unavailable until a signed-in browser session
  is connected. Because neither safe HTTPS route is active, the source has not been stopped.

The next safe action is to create a dedicated UAT-only Cloudflare Tunnel/hostname, verify the
external HTTPS route, and run authenticated plus physical-device UAT. Do not switch the final
`foodchainservice.com` route or change the source runtime without a separate cutover approval.
