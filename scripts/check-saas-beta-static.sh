#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

fail() { printf 'ERROR: %s\n' "$1" >&2; exit 1; }

saas_files=(
  backend/app/models/saas_billing.py
  backend/app/models/saas_privacy_support.py
  backend/app/schemas/saas_billing.py
  backend/app/schemas/saas_privacy_support.py
  backend/app/services/saas_billing_service.py
  backend/app/services/saas_privacy_support_service.py
  backend/app/routers/membership.py
  backend/app/routers/privacy_support.py
)

if rg -n 'impersonat(e|ion)_(token|session)|raw_(provider_)?payload|card_(number|token)|bank_account|client_secret' "${saas_files[@]}"; then
  fail "SaaS production surfaces contain a credential, raw-provider, or impersonation field"
fi
if rg -n '(^|[^[:alnum:]_])(delete|truncate)[[:space:]]*\(' backend/app/services/saas_privacy_support_service.py; then
  fail "Privacy/support service contains a destructive execution call"
fi
if git grep -En 'sk_live_[[:alnum:]]+|AKIA[0-9A-Z]{16}|BEGIN (RSA |OPENSSH )?PRIVATE KEY' -- backend/app frontend/src scripts docs; then
  fail "Tracked application surfaces contain a high-confidence secret marker"
fi
rg -q 'live_charging_enabled' backend/app/config.py || fail "billing live-charge guard is missing"
rg -q 'Approved, unexpired Tenant support access is required' backend/app/services/saas_privacy_support_service.py || fail "support access expiry guard is missing"

printf 'SaaS beta static boundary checks passed.\n'
