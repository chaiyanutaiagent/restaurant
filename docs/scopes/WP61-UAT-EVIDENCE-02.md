# WP61 UAT Evidence — Shared ERP and Combined Batch B

Date: 2026-09-22

Decision: WP61 SOFTWARE UAT PASS; WP59–WP61 COMBINED BATCH B PASS

Environment: UAT only (`restaurant-pos-uat-drill`)

Production: NO-GO / unchanged

## Immutable release identity

| Item | Evidence |
|---|---|
| WP61 backend source | commit `54bdb15` |
| QA context hotfix | commit `5b91631` |
| Backend image | `restaurant-pos-backend:wp61-54bdb15` / `sha256:efd078a338dfb66403fdc8cdc92d11aa97b0b8d234af38f6fcae7c9d703c8ba5` |
| Frontend image | `restaurant-pos-frontend:wp61-5b91631` / `sha256:05132ef5940052f5292d21d477e05bab1260e7d206af2a0e4bebee64de55b996` |
| Release archive SHA-256 | `1018676462fcd099aef9d5946b863d47d7e1345bbb17f64878b94dff1f126ad0` |
| Final public smoke | `/`, `/company/erp`, `/health` returned HTTP 200 |

The hotfix is frontend-only. It makes the QA banner select the active Tenant or
Platform token by route, prevents cross-surface context display and shows the
short-lived session expiry time.

## Backup and migration evidence

- Pre-deploy backup:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/wp61-before-20260922T132057Z`.
- Five PostgreSQL dumps, Redis and uploads were captured with a checksum file;
  `sha256sum -c` passed.
- `pg_restore -l` read each dump successfully: legacy 1,782 catalog entries,
  Platform 342, Restaurant 1,227, Retail 442 and Takeaway 174.
- Migration heads remained unchanged because WP61 adds no migration:
  legacy `wp60tenant0025`, Platform `p15platform0019`, Restaurant
  `p6restaurant0007`, Retail `p13retail0007` and Takeaway `p6takeaway0008`.
- No database restore or schema downgrade was required for application
  rollback.

## Automated and contract evidence

- Focused Company/ERP/Tax regression: 59/59 passed.
- Full backend regression: 534/534 passed.
- WP61 authority/UX contract suite: 8/8 passed.
- Frontend TypeScript and production build passed. Docker backend/frontend
  builds passed; the existing large-chunk warning is unchanged.
- Final UAT runtime logs after corrected restore contained zero Backend,
  Frontend, Nginx or Cloudflared critical/5xx lines.

## Authenticated persona matrix

The key and issued credentials were read only from protected UAT secret files.
No key, password or token is stored in this repository or evidence.

### Tenant surface

- Eight personas were issued successfully: Company Admin, Branch Manager,
  Cashier/Service, Kitchen, Accountant, Purchasing, Warehouse and Auditor.
- Company context, effective access, dashboard, Action Center and Shared ERP
  returned HTTP 200 for every persona and applied server-side visibility.
- Operational status returned 200 only to operationally relevant roles;
  Accountant, Purchasing and Warehouse returned the expected 403.
- Shared ERP returned four scoped areas. Permission-denied areas remained
  read-only rather than leaking their queues. Company Admin evidence contained
  two open exceptions, nine controls and five explicit release holds.

### Platform surface

- Three personas were issued successfully: Platform Admin, Platform Operator
  and Platform Auditor.
- Dashboard, Company and Audit reads matched effective Platform roles.
  Platform Operator received the expected 403 for Team while Admin/Auditor
  received 200.
- Requests without the QA access key returned 404. Legacy credentialless auto
  login also returned 404.

### Session safety

- QA sessions expire in about 30 minutes and the browser banner displays the
  active persona, scope and expiry time.
- Tenant logout changed a fresh access-token check from 200 to 401.
- Platform logout changed a fresh access-token check from 200 to 401.
- Tenant and Platform browser sessions were logged out after visual UAT.

## Visual UAT

- `/company/erp` passed at 1440×900 and 1024×768 without horizontal overflow.
- Company Dashboard, Action Center, App Launcher, Organization and People pages
  loaded with the correct Company/Branch context.
- Platform Dashboard, Companies, Team and Audit loaded without horizontal
  overflow or application console errors.
- Cashier visual evidence showed permission-denied ERP content instead of
  unauthorized detail.
- One UAT-only UI defect was found: a retained Tenant QA banner appeared on a
  Platform route. Commit `5b91631` fixed it and the corrected UAT build showed
  `platform_admin · Platform` on Platform, Company/Branch context on Tenant and
  no QA banner after logout.

## Rollback, restore and isolation

- The first rehearsal intentionally stopped at the health gate because the
  command omitted `docker-compose.uat.yml`; the QA safety validator rejected a
  Production environment with QA mode enabled. UAT was restored immediately.
- The corrected canonical command includes both
  `docker-compose.prod.yml` and `docker-compose.uat.yml`.
- App-only rollback to the pinned WP60 backend/frontend images became healthy
  in 10 seconds. Restore to WP61 became healthy in 10 seconds.
- Production container names, IDs and images were identical before and after
  rollback, restore and the frontend hotfix.
- Post-restore Backend was healthy and public root, Shared ERP and health
  checks returned HTTP 200.

## Holds preserved

- Real tax documents/e-Tax and real filing.
- Live payment/refund/provider execution.
- Accountant sign-off and external fiscal acceptance.
- Production deployment or Production flag changes.
- Retail data-source cutover.
- Takeaway/Central Kitchen transaction activation.
- Physical printer, cash, PromptPay and offline-network acceptance.

