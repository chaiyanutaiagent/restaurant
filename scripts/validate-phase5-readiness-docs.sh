#!/bin/sh
set -eu

required_files='docs/production/phase5-readiness-workbook.md
docs/production/device-uat-checklist.md
docs/production/operator-training-drill.md
docs/production/security-risk-acceptance.md
docs/scopes/P5-PRODUCTION-READINESS-05.md'

printf '%s\n' "$required_files" | while IFS= read -r path; do
  [ -f "$path" ] || {
    printf 'ERROR: required Phase 5 readiness document missing: %s\n' "$path" >&2
    exit 1
  }
done

grep -q 'physical_device_uat: pending' docs/production/phase5-readiness-workbook.md
grep -q 'production_activated: false' docs/production/phase5-readiness-workbook.md
grep -q 'phase6_started: false' docs/production/phase5-readiness-workbook.md
grep -q 'security_owner_decision: pending' docs/production/security-risk-acceptance.md
grep -q 'Platform Owner completion approval' docs/production/device-uat-checklist.md

printf 'PASS: Phase 5 readiness document package is complete and remains unsigned.\n'
