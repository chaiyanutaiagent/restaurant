# WP72 — Sketch Biz UAT Tenant

Status: UAT READY — Production HOLD

## Objective

Prepare the existing primary UAT tenant as `บริษัท สเก็ตช์ บีซ จำกัด` without changing Production or the read-only ERP-POS source.

## Legal profile

- Thai legal name: `บริษัท สเก็ตช์ บีซ จำกัด`
- English legal name: `SKETCH BIZ CO., LTD.`
- Company registration/tax ID: `0125568025206`
- Registered address: `63/5 หมู่ที่ 7 ถนนบางกรวย-ไทรน้อย ตำบลไทรน้อย อำเภอไทรน้อย จังหวัดนนทบุรี 11150`
- Currency: THB
- Time zone: Asia/Bangkok
- Fiscal year start: January (year end 31 December)

## UAT hierarchy

| Product | Brand | Branch code | UAT transaction state |
|---|---|---|---|
| Restaurant POS | ครัวป่าปลาเขื่อน | KPP-01 | Test data only |
| Restaurant POS | The Loft Kitchen | TLK-01 | Test data only |
| Retail POS | The Loft Mini Mart | TLM-01 | Test data only |
| Takeaway POS | Chambo | CHB-01 | HOLD / dark launch |

The setup reuses the approved primary UAT Company ID so existing test personas and automatic UAT access remain valid. It is idempotent and can be rerun after a UAT restore.

## Included controls

- Four active workspaces with explicit Brand, Branch and business database context.
- Canonical role presets for owner, manager, cashier, accounting, purchasing, warehouse, kitchen and other supported staff scopes.
- Super-admin access to all four branches.
- Thai VAT test rules for included VAT 7%, zero-rated and exempt examples.
- Two Restaurant examples, each with four menu categories and four dining zones (16 tables per Restaurant branch).
- Platform reference projection to Restaurant, Retail and Takeaway databases.
- One Android APK resolves the customer by business code; no rebuild per customer is required.
- Android UAT API and public QR links use `https://uat-takeaway.foodchainservice.com` rather than a local IP.

## Release holds

- `vat_registered=true` and the branch tax registrations are UAT test configuration. Confirm ภ.พ.20, the VAT effective date, actual registered branch codes and actual branch addresses before Production.
- Do not enable Takeaway transactions until the approved transaction and Physical UAT gates pass.
- Do not import the final Chambo source snapshot until source IDs, record counts, media inventory and reconciliation sign-off are available.
- Do not change `/Users/user/Projects/erp-pos-run`.

## Apply command

Run inside the UAT backend container only:

```text
python -m app.cli.prepare_sketch_biz_uat \
  --company-id 1b8a1818-44d6-4d5f-9d22-e5e17b23c081 \
  --username admin \
  --yes
```

Expected result: `ready_for_controlled_uat`, `production_activated=false`, `takeaway_transactions=hold`.
