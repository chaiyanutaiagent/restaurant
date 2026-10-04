# WP62 UAT Evidence — Takeaway Operational UI

Date: 2026-09-22

Decision: **WP62 FOCUSED SOFTWARE UAT PASS**

Environment: UAT only (`restaurant-pos-uat-drill`)

Production: **NO-GO / unchanged**

Batch decision: Batch C remains open. WP63 may begin on Local/UAT while every
Takeaway transaction write remains on Server-authoritative HOLD.

## Immutable release identity

| Item | Evidence |
|---|---|
| Source commit | `da889f9` |
| Backend image | `restaurant-pos-backend:wp62-da889f9` / `sha256:c5026dd7a2327bbf1227d228019c980986cc1a49f51cdf9c20c988bda84e03a1` |
| Frontend image | `restaurant-pos-frontend:wp62-da889f9` / `sha256:ce422a7148af9b793bb83fed92e9c3d88312017dcc5aadb463f0824895d8b4ea` |
| Release archive SHA-256 | `f98dce8744de073b12ba9c9fb7164d2379ea9d007a96f6c96aa177a50fa8d6b1` |
| Final UAT smoke | `/`, `/health`, `/health/ready` and `/takeaway` returned HTTP 200 |

The UAT runtime keeps `TAKEAWAY_FEATURE_ENABLED=true` for product review and
`TAKEAWAY_UAT_TRANSACTION_WRITES_ENABLED=false` for fail-closed transaction
control. Company Kitchen and Distribution writes remain disabled. QA Access
Mode remains UAT-only.

## Backup evidence

- Pre-deploy backup:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/wp62-before/restaurant-pos-prod-20260922T144441Z`.
- PostgreSQL legacy, Platform, Restaurant, Retail and Takeaway dumps plus
  uploads and Redis archives were captured.
- `sha256sum -c` passed for all seven artifacts.
- `pg_restore` catalog inspection passed: legacy 1,797 entries, Platform 357,
  Restaurant 1,242, Retail 457 and Takeaway 189.
- WP62 adds no database migration. No database restore or downgrade was needed
  during application rollback.

## Automated evidence

- Focused Backend Takeaway regression: 40/40 passed locally and again against
  the immutable remote candidate image.
- Browser Takeaway workspace suite: 6/6 passed.
- Frontend TypeScript, production build and backend/frontend Docker builds
  passed.
- Git diff whitespace gate passed.
- Final UAT Backend and Frontend logs contained zero matched critical,
  traceback or 5xx patterns after deployment.

## Authenticated UAT evidence

Protected QA Access Mode issued a short-lived Company Admin session scoped to
the synthetic Takeaway UAT branch. No QA key, password or token is stored in
this repository or evidence.

| Check | Result |
|---|---|
| Takeaway status | HTTP 200; `enabled=true`, `release_stage=dark_launch`, `writes_enabled=false` |
| Shift list before mutation attempt | HTTP 200; two records |
| Catalog categories | HTTP 200; eight records |
| Open-shift mutation | HTTP 409; `takeaway_write_hold` |
| Import dry-run | HTTP 200; read-only validation remained available |
| Cutover preview | HTTP 200; read-only preview remained available |
| Shift list after mutation attempt | HTTP 200; still two records |
| Post-restore status/mutation | HTTP 200 / 409 with writes still disabled |

The UAT Company Admin and Branch Manager identities received an audited,
non-default assignment to the synthetic Takeaway branch so the signed context
could be tested. This is UAT identity fixture data covered by the pre-deploy
backup; it is not a Takeaway operational transaction or Production change.

## Rollback, restore and isolation

- App-only rollback used both `docker-compose.prod.yml` and
  `docker-compose.uat.yml`.
- UAT Backend/Frontend rolled back to
  `restaurant-pos-backend:wp61-54bdb15` and
  `restaurant-pos-frontend:wp61-5b91631`.
- The rollback Backend became healthy and root/health returned HTTP 200 in
  11 seconds.
- UAT then restored to the immutable WP62 images; root, health, readiness and
  Takeaway returned HTTP 200. The complete rollback/restore rehearsal took
  22 seconds.
- PostgreSQL, Redis, Nginx and Cloudflared were not recreated. The WP62 image
  pins remained in `.env.uat`.
- Production Backend, Frontend, Nginx, PostgreSQL, Redis and Cloudflared
  container IDs and images remained identical before and after deployment and
  rehearsal.

## Holds preserved

- Real Takeaway sales, shifts, payments, refunds, stock, production,
  transfers, credits, ERP acknowledgement and public-order writes.
- Chambo real-data cutover and Cutover Execute.
- Central Kitchen and Distribution writes.
- Live payment/refund provider and real tax/credit-note execution.
- Physical printer, cash drawer, tablet, PromptPay and network-loss acceptance.
- Owner/canary approval and all Production deployment or Production flags.

## Next gate

WP63 may activate Central Kitchen and Supply Chain UI on Local/UAT with
read-only/dark-launch defaults. Stock, QC, opening-lot, production, transfer
and recall writes must stay Server-authoritatively gated until their separate
readiness and owner/canary gates pass. Full persona, visual, regression and
rollback acceptance remains the combined Batch C gate after WP64.
