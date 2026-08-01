#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
OUTPUT_ROOT="${TENANT_EXPORT_ROOT:-backups/tenant-exports}"
COMPANY_ID=""
REASON=""

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --company-id)
      [ "$#" -ge 2 ] || fail "--company-id requires a UUID"
      COMPANY_ID="$2"
      shift 2
      ;;
    --reason)
      [ "$#" -ge 2 ] || fail "--reason requires text"
      REASON="$2"
      shift 2
      ;;
    --output-root)
      [ "$#" -ge 2 ] || fail "--output-root requires a path"
      OUTPUT_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[ -n "$COMPANY_ID" ] || fail "--company-id is required"
[ -n "$REASON" ] || fail "--reason is required"
[ -f "$COMPOSE_FILE" ] || fail "compose file not found: $COMPOSE_FILE"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_dir="${OUTPUT_ROOT%/}/${COMPANY_ID}/${timestamp}"
artifact="$output_dir/tenant-export.json"
mkdir -p "$output_dir"
chmod 700 "$output_dir"

printf 'Exporting Company %s across configured database boundaries...\n' "$COMPANY_ID"
docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  python -B -m app.utils.export_tenant \
  --company-id "$COMPANY_ID" \
  --reason "$REASON" > "$artifact"
chmod 600 "$artifact"

content_sha256="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["content_sha256"])' "$artifact")"
artifact_sha256="$(sha256_file "$artifact")"
cat > "$output_dir/manifest.txt" <<EOF
scope=P5-TENANT-RESILIENCE-02
timestamp=$timestamp
company_id=$COMPANY_ID
artifact=tenant-export.json
artifact_sha256=$artifact_sha256
content_sha256=$content_sha256
credential_redaction=true
reason=$REASON
EOF
chmod 600 "$output_dir/manifest.txt"

printf 'Tenant export completed: %s\n' "$artifact"
printf 'Content SHA-256: %s\n' "$content_sha256"
