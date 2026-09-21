# WP49 UAT Evidence

Date: 2026-09-21  
Environment: UAT only  
Decision: **PASS**

## Deployment identity

| Item | Evidence |
|---|---|
| Feature commit | `00a4868` (`feat: implement WP49 restaurant order entry`) |
| Final UAT candidate | `9ff3e22` (`fix: load WP49 UAT restaurant menu`) |
| Release directory | `/home/behappyaiagent/restaurant-uat-releases/9ff3e22` |
| Frontend image | `restaurant-pos-frontend:wp49-9ff3e22` |
| Frontend image ID | `sha256:e506b37fba82c337e18673ec8607572d2574412f984ca2970c08098ff953c952` |
| UAT stack | `restaurant-pos-uat-drill` |
| Backend | Unchanged: `restaurant-pos-backend:wp48-486a259` |
| Database migration | None |

The initial candidate exposed a UAT-only catalogue loading defect: the client requested `limit=200`, while the Server contract allows at most 100. The final candidate changed the bounded request to 100 and retained the signed Restaurant catalogue scope.

## Local engineering gate

- Frontend TypeScript: PASS.
- Frontend production/PWA build: PASS, with the existing large-chunk advisory.
- No backend or database contract changed.
- The client submits `expected_unit_price`, `cart_version` and a stable idempotency key; the Server remains authoritative for price and ticket creation.

## Browser UAT

### Staff order composer

| Check | Result |
|---|---|
| Signed role | Branch Manager through the real login path |
| Restaurant catalogue | 28 menu items |
| Category navigation | 7 unique labels including `ทั้งหมด`; all legacy duplicate-category products remained reachable |
| Desktop 1440×900 | No horizontal overflow; 66 visible controls; no control below 44×44px |
| Tablet landscape 1024×768 | No horizontal overflow; no visible control below 44×44px |
| Product options | Quick options explicitly state that they are saved as notes and do not change price |
| Cart line identity | The same product with and without `หวานน้อย` produced two separate cart lines |
| Server price notice | Visible before Kitchen submission |

### End-to-end Kitchen path

A bounded UAT transaction was submitted from active table A1:

- Staff order reference: `DO-21033204-C708`.
- Item: `น้ำเปล่า` ×1.
- Server-accepted amount: ฿15.00.
- Session changed from 1 to 2 orders and total changed from ฿89.00 to ฿104.00.
- KDS showed the new table A1 item in the `รอทำ` lane under the beverage station.
- The UI reported `เพิ่มออเดอร์แล้ว`; no optimistic success was shown before the Server response.

### Table and QR workspace

- The active session-scoped QR and existing Customer QR order remained visible.
- Four operating zones A–D and their test tables remained available; pre-existing UAT diagnostic tables were not deleted.
- Table actions remained branch-scoped and the final header/action touch targets use the shared 44px baseline.

## Role and authentication smoke

The temporary Branch Manager browser password was restored from the Server-held UAT secret file. No password is stored in Git or this evidence file. The formal smoke then passed:

| Role | Expected landing | Result |
|---|---|---|
| Cashier | `/pos` | PASS; Restaurant catalogue 28 |
| Branch Manager | `/restaurant` | PASS; Restaurant catalogue 28 |
| Accountant | `/company` | PASS; catalogue correctly denied by role |
| Purchasing | `/admin` | PASS; Restaurant catalogue 28 |

Automatic login remained absent (`404`) and auth bypass remained disabled.

## Rollback rehearsal

- WP49 → WP48 frontend-only rollback: 1 second.
- Public UAT health check: PASS.
- WP48 → WP49 restore: 1 second.
- Backend container identity remained unchanged during both operations.
- Final UAT frontend image was restored to `restaurant-pos-frontend:wp49-9ff3e22`.

## Production isolation

Production remained untouched and retained its pre-WP49 identities:

| Service | Image | Container ID |
|---|---|---|
| Backend | `restaurant-pos-backend:auth-a0fdccf` | `f6e08435721a` |
| Frontend | `restaurant-pos-frontend:ui-e4200ca` | `857e0dbab1a2` |
| Nginx | `restaurant-pos-nginx:unified-d528512` | `aea97e7f90f7` |
| Cloudflared | `cloudflare/cloudflared:2026.7.0` | `ae6862f8a09f` |
| PostgreSQL | `postgres:15-alpine` | `3565e3fd72ad` |
| Redis | `redis:7-alpine` | `76658d7ad2fd` |

No Production flag, migration, data-source change, payment/tax provider or transaction path was enabled.
