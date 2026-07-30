# Production Smoke Test And UAT Checklist

Use this after every production deploy, rollback, migration, and HTTPS activation. The automated smoke test is intentionally non-destructive by default.

## Automated Smoke Test

Run against local HTTP production mode:

```sh
./scripts/smoke-production.sh .env.production
```

Run against HTTPS:

```sh
PRODUCTION_SMOKE_BASE_URL=https://$SERVER_NAME ./scripts/smoke-production.sh .env.production
```

The script validates `.env.production`, runs the production status check, and verifies:

- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `GET /`

To skip the Docker-backed status check when testing through a remote load balancer:

```sh
PRODUCTION_SMOKE_SKIP_STATUS=1 PRODUCTION_SMOKE_BASE_URL=https://$SERVER_NAME ./scripts/smoke-production.sh .env.production
```

## Optional Auth Smoke

Auth smoke is read-only and only runs when all required variables are set. It logs in, stores the access token only in process memory, and checks `GET /api/v1/auth/me`. It never prints passwords, tokens, or authorization headers.

```sh
SMOKE_TEST_EMAIL=uat-admin@example.com \
SMOKE_TEST_PASSWORD='use-a-secret-source' \
SMOKE_TEST_COMPANY_ID='00000000-0000-0000-0000-000000000000' \
./scripts/smoke-production.sh .env.production
```

If the test user should bind to a branch, also set:

```sh
SMOKE_TEST_BRANCH_ID='00000000-0000-0000-0000-000000000000'
```

## When To Run

- After deploy.
- After rollback.
- After production migrations.
- After HTTPS activation.
- After certificate renewal if nginx was reloaded.
- After restoring data in an isolated drill.

## Manual UAT Checklist

Use a clearly marked UAT user and UAT data. Avoid using real customer payment data unless the business has approved the test.

- [ ] Login succeeds for an admin or UAT operator.
- [ ] Logout clears the session.
- [ ] Create a category with a recognizable UAT name.
- [ ] Create a product with SKU, price, tax settings, and category.
- [ ] Upload a product image that matches the production allowed file types and size.
- [ ] Edit the product name, price, or active state.
- [ ] Confirm product/category changes appear in the product list and public storefront where expected.
- [ ] Open a POS shift if the workflow requires it.
- [ ] Complete a POS sale or order using an approved test payment method.
- [ ] Confirm payment status is correct.
- [ ] Print or view the receipt.
- [ ] Confirm stock movement or stock balance changed as expected.
- [ ] Confirm the sale appears in sales reports.
- [ ] Confirm user/admin permissions restrict access to at least one protected admin area.
- [ ] Restart the stack and confirm login, product, sale, upload, and stock data persist.
- [ ] Run a backup after the real UAT transaction.
- [ ] Run a restore drill in an isolated `COMPOSE_PROJECT_NAME` environment using that backup.

## Pass / Fail Sign-Off

Record each production validation:

```text
date_utc:
release_or_commit:
environment:
base_url:
operator:
automated_smoke: pass/fail
manual_uat: pass/fail
backup_after_uat: pass/fail/not_applicable
restore_drill: pass/fail/not_applicable
notes:
go_no_go_decision:
approver:
```

## Known Limitations

- Automated business smoke tests do not create categories, products, stock, sales, payments, or receipts yet.
- Auth smoke requires an existing test user and company ID.
- Payment gateway tests must use approved sandbox or business-approved test methods.
- Restore drills should run only in isolated Compose projects, not against live production data.
- Browser-level automated UAT is not implemented yet.
