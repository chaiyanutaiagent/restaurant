# WP72 — Sketch Biz UAT Evidence

Date: 2026-09-27

Environment: UAT only

Decision: PASS — tenant structure and bounded smoke complete; Production HOLD

## Release identity

- Repository: `chaiyanutaiagent/restaurant`
- Branch: `codex/foodchainservice-platform`
- Takeaway UI and tenant implementation: `b18b2ac`
- Tax database-boundary correction: `499210a`
- Restaurant sample inventory-role correction: `ee929cf`
- Backend image: `restaurant-pos-backend:wp72-ee929cf`
- Backend image ID: `sha256:8c4b5a4761ef5589061dcd99da80b640c8686afe83cb328e5087bbaa2bf4cb3e`
- Frontend image: `restaurant-pos-frontend:wp72-b18b2ac`
- Frontend image ID: `sha256:d54fb9a7b3ccbd5f727525a903b715e3c57fd03252ec4f041e7279a1ad4c69e0`
- UAT stack: `restaurant-pos-uat-drill`

## Rollback checkpoint

- Backup: `/home/behappyaiagent/restaurant-uat-deploy-backups/wp72-before-b18b2ac`
- Five PostgreSQL custom-format dumps exist for Legacy, Platform, Restaurant, Retail and Takeaway.
- Every dump passed `pg_restore --list` before deployment.
- Every dump passed the stored SHA-256 manifest after deployment.
- Previous UAT backend/frontend images and immutable releases remain available.

## Applied company structure

| Product | Brand | Branch | Result |
|---|---|---|---|
| Restaurant | ครัวป่าปลาเขื่อน | KPP-01 | Active |
| Restaurant | The Loft Kitchen | TLK-01 | Active |
| Retail | The Loft Mini Mart | TLM-01 | Active |
| Takeaway | Chambo | CHB-01 | Active, transactions HOLD |

Verified company profile:

- `บริษัท สเก็ตช์ บีซ จำกัด`
- `SKETCH BIZ CO., LTD.`
- Registration/tax ID `0125568025206`
- Business code `sketch-biz`
- THB, Asia/Bangkok, fiscal year starts January
- 2 Restaurant brands, 1 Retail brand and 1 Takeaway brand
- 4 intended active branches
- 16 canonical role presets
- 32 WP72 Restaurant tables across two brands, plus pre-existing UAT fixtures
- 8 WP72 Restaurant menu products across four categories per brand, plus pre-existing UAT fixtures

## Tax boundary

- UAT test rate: VAT 7%, price included.
- Zero-rated and exempt examples are available for UI/workflow testing.
- The Revenue Department lists the reduced 7% rate through 30 September 2570: `https://www.rd.go.th/1603.html`.
- Production remains blocked until ภ.พ.20, VAT effective date, registered branch codes, branch addresses and filing setup are confirmed.
- No real tax document was generated or submitted.

## Smoke result

- Company `/company`: HTTP 200.
- Restaurant `/restaurant/pos`: HTTP 200.
- Retail `/retail/pos`: HTTP 200.
- Takeaway `/takeaway/store/orders`: HTTP 200.
- Readiness endpoint: HTTP 200.
- UAT automatic login: HTTP 200 on all four product hosts.
- Public `sketch-biz` lookup returned the approved company ID and legal name.
- Backend remained healthy after the final apply.

## Detected and corrected during apply

1. The first apply attempted tax rows in Platform, while the tax schema belongs to Legacy. The Platform transaction rolled back automatically; commit `499210a` moved tax setup to the correct database after reference projection.
2. The first Restaurant example insert used an unsupported inventory role. That example-data transaction rolled back automatically; commit `ee929cf` uses the supported `not_stocked` role.
3. The final idempotent apply completed with `ready_for_controlled_uat` and no duplicate workspace, role or admin-access creation.

## Final release flags

- `TAKEAWAY_FEATURE_ENABLED=true`
- `TAKEAWAY_UAT_TRANSACTION_WRITES_ENABLED=false`
- `UAT_AUTH_BYPASS_ENABLED=true`
- Physical printer, cash, PromptPay and network-loss UAT remains deferred by the owner.
- Final Chambo source snapshot/import remains `not_started`; the mapping contract is dry-run only.
- Production deployment and Production flags were not changed.

## Production isolation

Production container IDs and image tags remained unchanged for Backend, Frontend, PostgreSQL, Redis, Nginx and Cloudflared. Only the UAT Backend and Frontend services were recreated; UAT PostgreSQL, Redis, Nginx and Cloudflared were not recreated.
