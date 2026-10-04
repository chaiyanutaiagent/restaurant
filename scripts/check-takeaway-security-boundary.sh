#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if git grep -I -n -E 'BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|sk-[A-Za-z0-9]{32,}' -- backend/app frontend/src frontend/android scripts .env.example; then
  echo "FAIL: credential-like value found in tracked runtime source" >&2
  exit 1
fi

if grep -R -n -E 'app\.models\.(restaurant|retail)|get_(restaurant|retail)_service_db' backend/app/services/takeaway*.py backend/app/routers/takeaway.py; then
  echo "FAIL: Takeaway runtime reaches another operational boundary" >&2
  exit 1
fi

if grep -R -n -E 'com\.chambo|com\.chaiyanutaiagent\.restaurant' frontend/android/app/src frontend/capacitor.config.ts; then
  echo "FAIL: legacy Android application identity remains" >&2
  exit 1
fi

echo "PASS: tracked secret scan, operational DB boundary and Android identity"
