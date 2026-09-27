# WP73 — Automated UAT Completion

Date: 2026-09-27

Environment: Local build + UAT artifact storage

Decision: **AUTOMATED GATE PASS — human/physical gates deferred**

Production: **HOLD / unchanged**

## Android UAT candidate

- Artifact: `releases/uat/foodchainservice-takeaway-1.1.0-uat.2.apk`
- Package: `com.foodchainservice.takeaway.uat`
- Version: `1.1.0-uat.2` (`versionCode 10101`)
- SDK: minimum 23, target 35
- Signature: Android debug certificate; v1/v2 verification PASS
- Embedded checks: UAT Takeaway host, Takeaway route and `sketch-biz` business code present
- SHA-256: `06fccc9e8f8bb182ecf12479aa096552c31d87f240d44dbcf9255b2331e213a1`

The artifact and checksum are archived read-only on UAT at:
`/home/behappyaiagent/restaurant-uat-releases/android/`

This is a debug-signed internal UAT build, not a Production APK.

## Chambo source dry-run

Source repository stayed read-only and unchanged:

- Repository: `chaiyanutaiagent/erp-pos-run`
- Source commit: `24e9300bde16c5be72f9eb56bad74fb59401bd06`
- Source company: `Test Company`
- Source brand: `chambo` / `ฉ่ำโบ๊ะ หมูย่างกะทิ`
- Selected source branch: `BKK-01` / `สาขากรุงเทพ`, identified for this
  migration as the Ozone One branch by owner instruction
- Excluded source branch: `BKK-02` / `สาขาบางนา`
- Target: Sketch Biz / Chambo / `CHB-01` / `Chambo สาขาโอโซนวัน`
- Mapping policy: single branch only; no cross-branch consolidation
- The idempotent UAT tenant preparation was reapplied successfully with the
  Ozone One branch name; Takeaway transactions remained `HOLD`.

The exporter was made compatible with the legacy source schema by using
`created_at` as the stable order and fallback business time when the legacy
`sale_orders.business_at` column is absent.

Snapshot:

- ID: `chambo-20260927T075215.704279Z-cf242092`
- Cutoff: `2026-09-27T07:52:15.704279Z`
- Open operations: 0 in all seven checked classes
- Categories: 4
- Items: 25
- Recipes: 8
- Units: 8
- Stock locations: 2
- Opening stock rows: 6
- Opening credit rows: 1
- Historical records: 0
- Total records: 54

Signed validation and preview:

- Seal: Ed25519 verified
- Bundle findings: 0
- Preview blockers: 0
- Preview ready: true
- Manifest digest: `3ae12c86446655743be64aed08fc5c86d83fcd7b868c2d7ff5a0e6c57a6f9569`
- Mapping digest: `232cf440178888635bc4490dfdb14386a52cb30edd16a0e41b8bebeda14b67f1`
- Preview digest: `294784019e6653c411690af1460290927dcaeb167387498e6cd039d30c73e0cf`
- Opening stock on hand: `60000.0000`
- Opening stock reserved: `0.0000`
- Opening stock value: `0.00000000`
- Opening credit balance: `0.00`

The sealed bundle and public verification key are archived on UAT at:

`/home/behappyaiagent/restaurant-uat-imports/wp73-chambo-dry-run/chambo-wp73-uat-ozone-one-signed-bundle.tgz`

Archive SHA-256:
`21eddd0b450112f7fbea57d0b9ec4a0bf389f7bfdd34f1b4f2d508fe0278fd3a`

The earlier two-branch archive was removed from UAT after the Ozone One-only
archive passed verification, preventing an accidental BKK-02 import.

The temporary private signing key was removed after verification and was not
committed or uploaded.

## Deliberately not executed

- No Chambo data was applied to the target database.
- No Takeaway transaction-write flag was enabled.
- No Production container, image, database, hostname or flag was changed.
- No real tax document was issued.
- No physical Android installation, printer, cash, PromptPay, offline/reconnect,
  orientation or operator acceptance test was claimed.

## Remaining human gates

1. The owner-selected scope is `BKK-01` / Ozone One only; Data/Privacy approval
   of the sealed cutoff remains required before target execution.
2. Take a fresh target backup and record the rollback reference immediately
   before target execution.
3. Execute UAT import, replay once for idempotency and reconcile the exact
   target counts/control totals.
4. Install `1.1.0-uat.2` on a physical Android device and complete the deferred
   printer/payment/network-loss checklist.
5. Production remains a separate go/no-go decision.
