# WP74 — Sketch Biz Chambo UAT Cutover

Date: 2026-09-27

Environment: UAT only (`restaurant-pos-uat-drill`)

Decision: **AUTOMATED UAT DATA GATE PASS / HUMAN GATES DEFERRED / PRODUCTION HOLD**

## Approved target

- Company: `บริษัท สเก็ตช์ บีซ จำกัด` (`1b8a1818-44d6-4d5f-9d22-e5e17b23c081`)
- Brand: Chambo (`d6391cbe-ee53-4873-b95b-219c9bc23e7c`)
- Branch: `BKK-01` / `Chambo สาขาโอโซนวัน`
- Source scope: Chambo source branch `BKK-01` only; source `BKK-02` excluded

The old unlinked Legacy fixture that previously occupied `BKK-01` was preserved
as branch `LEG-BKK-01-68485ba7` and deactivated. Its UUID and historical foreign
keys were retained. Platform and Legacy now project the active Chambo branch as
`BKK-01` with the same target UUID.

## Backup and signed bundle

- Pre-cutover five-database backup:
  `/home/behappyaiagent/restaurant-uat-deploy-backups/wp74-before-chambo-bkk01-20260927T1500`
- Every SHA-256 manifest entry passed.
- Every PostgreSQL custom-format dump passed `pg_restore --list`.
- Final snapshot: `chambo-20260927T081930.050911Z-385097c3`
- Signed bundle:
  `/home/behappyaiagent/restaurant-uat-imports/wp74-chambo-bkk01/chambo-wp74-uat-bkk01-signed-bundle.tgz`
- Archive SHA-256: `3a1b034ad7ec8c3efbd891eeb19bc0bb2955e6a22fda9823f2eae82ea0caf7cf`
- Key ID: `wp74-uat-chambo-bkk01`
- Mapping digest: `3c62a2e0924bd72e9939275845ba9021c7c6dcedcaec52c2fa8c0cfe3b3c87f3`
- Sealed manifest digest: `d8ff555fbabdfa63f61600fd6101ee714a4b49cae1e791f9f83b94c7076a35a8`
- Bundle validation findings: 0

The temporary private Ed25519 key was removed and was never uploaded or
committed. The WP73 bundle was moved to `superseded/` to prevent accidental use.

## Target execution and replay

- Cutover run: `a1bf2922-eb88-4c59-9a56-3de03a0b752b`
- Import batch: `441cde14-8c9a-4c90-8095-68a4ed6b8f1c`
- Execution key: `wp74-chambo-bkk01-20260927`
- Preview digest: `fceded3b6661eea7dc49a9a7b77473de5fe7bf8b6c1d538057919803d1a54436`
- Source records: 54
- Target import records: 54
- Rejected: 0
- Imported: 52
- Reused safely: 2 (`PCS` unit and the existing zero-impact branch credit target)
- Replay: PASS — returned the same cutover run and created no second batch
- Historical side effects: 0

Control totals matched exactly:

- opening stock on hand: `60000.0000`
- reserved: `0.0000`
- stock value: `0.00000000`
- opening credit balance: `0.00`
- historical sales total: `0`

Post-import Chambo target totals are 8 units, 12 categories, 45 items, 5 stock
locations and 8 recipes, including the retained synthetic UAT examples.

## Runtime boundary

- Commit: `f8b6d24`
- Immutable release: `/home/behappyaiagent/restaurant-uat-releases/f8b6d24`
- Source archive SHA-256: `a1c449ca172b7fd396bbbafabe31747faf74d0cea33ed990dd1dfa8e80be33f6`
- Backend image: `restaurant-pos-backend:wp74-f8b6d24`
- Backend image ID: `sha256:ae74be288f580b76f182b33dd906a5208d78e136437628acc458163a0124d9b3`
- Backend health: healthy; public readiness: HTTP 200
- `TAKEAWAY_UAT_TRANSACTION_WRITES_ENABLED=false`
- Takeaway transactions remain `HOLD`.
- No Production container, database, hostname, flag or data was changed.
- No real provider, PromptPay, tax submission or fiscal document was executed.

Only the UAT Backend container was recreated. UAT PostgreSQL, Redis, Frontend,
Nginx and Cloudflared retained their container identities. Every Production
container ID and image matched the pre-deploy snapshot.

## Deferred human gates

1. Install and accept the UAT APK on a physical Android device.
2. Test printer, cash drawer, PromptPay, tablet camera/touch/orientation and real
   network loss/reconnect.
3. Privacy Owner reviews the migrated sample/master data and retention scope.
4. Accountant confirms ภ.พ.20, registered branch number/address, VAT effective
   date and actual fiscal document sequence.
5. Product Owner reviews real staff/master data, disables UAT login bypass and
   separately approves Production go-live.
