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
- Source branches: `BKK-01`, `BKK-02`
- Target: Sketch Biz / Chambo / `CHB-01`
- Mapping policy: consolidate the two legacy branches into the target UAT branch

The exporter was made compatible with the legacy source schema by using
`created_at` as the stable order and fallback business time when the legacy
`sale_orders.business_at` column is absent.

Snapshot:

- ID: `chambo-20260927T073749.051182Z-ded0284f`
- Cutoff: `2026-09-27T07:37:49.051182Z`
- Open operations: 0 in all seven checked classes
- Categories: 4
- Items: 25
- Recipes: 8
- Units: 8
- Stock locations: 3
- Opening stock rows: 12
- Opening credit rows: 2
- Historical records: 0
- Total records: 62

Signed validation and preview:

- Seal: Ed25519 verified
- Bundle findings: 0
- Preview blockers: 0
- Preview ready: true
- Manifest digest: `1cb2c90e6152ab3d68c61f7af10d3ab21eda27176c04e9403c35124710b507d9`
- Mapping digest: `5ac42b9fd32e650fb717d36306e0c52c1a6aff0ecedc80acbe6fe5af0311650c`
- Preview digest: `59670c1c2a16ed6a21f5e5ae0c04bc61e79a9492f1b23c662405b13bb48b222b`
- Opening stock on hand: `120000.0000`
- Opening stock reserved: `0.0000`
- Opening stock value: `0.00000000`
- Opening credit balance: `0.00`

The sealed bundle and public verification key are archived on UAT at:

`/home/behappyaiagent/restaurant-uat-imports/wp73-chambo-dry-run/chambo-wp73-uat-signed-bundle.tgz`

Archive SHA-256:
`7e34f4e0ecd4caf84bf21feb362002af4984ad74a0481c0bcd49e2439c959392`

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

1. Data Owner and Privacy Owner approve the sealed source snapshot and the
   two-to-one branch consolidation policy.
2. Take a fresh target backup and record the rollback reference immediately
   before target execution.
3. Execute UAT import, replay once for idempotency and reconcile the exact
   target counts/control totals.
4. Install `1.1.0-uat.2` on a physical Android device and complete the deferred
   printer/payment/network-loss checklist.
5. Production remains a separate go/no-go decision.
