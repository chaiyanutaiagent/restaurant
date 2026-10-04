# WP48 UAT Evidence

Date: 2026-09-21  
Environment: UAT only  
Decision: **PASS**

## Deployment identity

| Item | Evidence |
|---|---|
| Git candidate | `486a259` (`fix: enlarge company shell brand target`) |
| Release directory | `/home/behappyaiagent/restaurant-uat-releases/486a259` |
| Backend image | `restaurant-pos-backend:wp48-486a259` |
| Backend image ID | `sha256:c5885b2249071389506c3e53b8423c0bf7b6a67cb049a0cb2a4cbe18b88a6d7b` |
| Frontend image | `restaurant-pos-frontend:wp48-486a259` |
| Frontend image ID | `sha256:ea5575679f3be583b868b60a41fa8460236b838eb2e0c317a4b7089b60d1a26d` |
| UAT stack | `restaurant-pos-uat-drill` |
| Auth bypass | `UAT_AUTH_BYPASS_ENABLED=false` |
| Identity database | `platform_core` |
| Backend health | Docker health `healthy`; `/health` returned `{"status":"ok","version":"1.0.0"}` |

## Role and permission smoke

The four formal UAT identities were prepared from canonical role presets and exercised through the real authentication path:

| Role | Expected landing | Result |
|---|---|---|
| Cashier | `/pos` | PASS; signed Restaurant context; catalogue 28 |
| Branch Manager | `/restaurant` | PASS; signed Restaurant context; catalogue 28 |
| Accountant | `/company` | PASS |
| Purchasing | `/admin` | PASS; signed Restaurant context; catalogue 28 |

Automatic login was absent (`404`). The temporary browser-test password was restored through the bounded UAT preparation command after the browser check; no password is stored in Git or this evidence file.

## Browser evidence

### Company shell

| Viewport | Result |
|---|---|
| Desktop 1440×900 | No horizontal overflow; Company/Branch context, Action Center and Device/Sync state present; Product readiness region present; Hotel PMS absent |
| Tablet 1024×768 | No horizontal overflow; all 19 visible interactive controls met the 44px target; Hotel PMS absent |

The accessible page tree exposed the `Product readiness` region and the Company, Branch and role context. The visually hidden skip link was excluded from touch-target measurement because it appears only on keyboard focus.

### Restaurant POS

| Check | Result |
|---|---|
| Allowed catalogue | 28 menu items |
| Category groups | 7 unique labels: ทั้งหมด, ของหวาน, เครื่องดื่ม, จานหลัก, เมนูพิเศษ, อาหาร, อาหารทานเล่น |
| Raw/Retail leakage | Not observed |
| Desktop 1440×900 | No horizontal overflow; 44px control baseline passed |
| Tablet 1024×768 | No horizontal overflow; category, product and cart panels fit; 44px control baseline passed |

The final candidate changes after the POS measurement were limited to Company shell visibility/touch-target corrections; the POS implementation and server catalogue boundary were unchanged.

## Backup and rollback

- Pre-deployment backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/wp48-before/restaurant-pos-prod-20260921T010310Z`.
- Database catalogue inspection, upload archive integrity, Redis archive integrity and recorded checksums passed.
- WP48 → WP47 app-only rollback: 11 seconds; health passed.
- WP47 → WP48 restore: 13 seconds; health and formal-role smoke passed.

## Production isolation

Production remained untouched. Final identities matched the pre-drill baseline:

| Service | Image | Container ID |
|---|---|---|
| Backend | `restaurant-pos-backend:auth-a0fdccf` | `f6e08435721a` |
| Frontend | `restaurant-pos-frontend:ui-e4200ca` | `857e0dbab1a2` |
| Nginx | `restaurant-pos-nginx:unified-d528512` | `aea97e7f90f7` |
| Cloudflared | `cloudflare/cloudflared:2026.7.0` | `ae6862f8a09f` |
| PostgreSQL | `postgres:15-alpine` | `3565e3fd72ad` |
| Redis | `redis:7-alpine` | `76658d7ad2fd` |

No Production flag, migration, data source, payment/tax provider or transaction path was enabled.
