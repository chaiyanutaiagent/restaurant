#!/bin/sh
set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_ROOT="${PROJECTION_BACKUP_ROOT:-backups}"
ASSUME_YES=0
EXPECTED_LEGACY_HEAD="6b7c8d9e0f12"
EXPECTED_PLATFORM_HEAD="p1platform0003"
EXPECTED_RESTAURANT_HEAD="p1restaurant0003"
FAILURE_EVENT_ID=""

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  if [ -n "$FAILURE_EVENT_ID" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
      sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -c "DELETE FROM reference_outbox WHERE id = '\''$1'\''" >/dev/null' \
      sh "$FAILURE_EVENT_ID" || true
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --backup-root)
      [ "$#" -ge 2 ] || fail "--backup-root requires a path"
      BACKUP_ROOT="$2"
      shift 2
      ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[ "$ASSUME_YES" = "1" ] || fail "this rehearsal writes only boundary target databases; pass --yes"
[ -f "$COMPOSE_FILE" ] || fail "compose file not found: $COMPOSE_FILE"
trap cleanup EXIT HUP INT TERM

docker compose -f "$COMPOSE_FILE" up -d postgres redis >/dev/null
tries=0
until docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; do
  tries=$((tries + 1))
  [ "$tries" -lt 30 ] || fail "postgres service did not become ready"
  sleep 2
done

legacy_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$POSTGRES_DB"')"
platform_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$PLATFORM_POSTGRES_DB"')"
restaurant_database="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c 'printf %s "$RESTAURANT_POSTGRES_DB"')"
if [ "$legacy_database" = "$platform_database" ] || \
   [ "$legacy_database" = "$restaurant_database" ] || \
   [ "$platform_database" = "$restaurant_database" ]; then
  fail "legacy, Platform and Restaurant database names must be distinct"
fi

legacy_head_before="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' | tr -d '[:space:]')"
[ "$legacy_head_before" = "$EXPECTED_LEGACY_HEAD" ] || fail "unexpected legacy head: $legacy_head_before"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT%/}/p1-reference-projection-05-${timestamp}"
mkdir -p "$backup_dir"
printf 'Backing up Platform and Restaurant targets before rehearsal...\n'
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB"' > "$backup_dir/platform-before.dump"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB"' > "$backup_dir/restaurant-before.dump"

cat > "$backup_dir/manifest.txt" <<EOF
scope_id=P1-REFERENCE-PROJECTION-05
rehearsal_status=backup_complete
snapshot_timestamp_utc=$timestamp
legacy_database=$legacy_database
legacy_migration_head=$legacy_head_before
platform_database=$platform_database
restaurant_database=$restaurant_database
runtime_system_of_record=legacy
contents=platform-before.dump restaurant-before.dump manifest.txt
EOF

printf 'Building projector image and applying independent migrations...\n'
docker compose -f "$COMPOSE_FILE" build backend >/dev/null
COMPOSE_FILE="$COMPOSE_FILE" scripts/run-boundary-migrations.sh >/dev/null

platform_head="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' | tr -d '[:space:]')"
restaurant_head="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' | tr -d '[:space:]')"
[ "$platform_head" = "$EXPECTED_PLATFORM_HEAD" ] || fail "unexpected Platform head: $platform_head"
[ "$restaurant_head" = "$EXPECTED_RESTAURANT_HEAD" ] || fail "unexpected Restaurant head: $restaurant_head"

operational_locations_before="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB" -tAc "
    SELECT md5(COALESCE(string_agg(value, '\''|'\'' ORDER BY value), '\'''\''))
    FROM (
      SELECT id::text || '\'':'\'' || COALESCE(central_location_id::text, '\'''\'') || '\'':'\'' || COALESCE(central_ready_location_id::text, '\'''\'') AS value FROM brands
      UNION ALL
      SELECT id::text || '\'':'\'' || COALESCE(store_location_id::text, '\'''\'') AS value FROM brand_branches
    ) preserved
  "
')"

printf 'Seeding deterministic snapshot events and draining the projector...\n'
seed_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  python -m app.utils.project_platform_references --seed-snapshot)"
printf '%s\n' "$seed_output"
drain_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  python -m app.utils.project_platform_references --drain --verify)"
printf '%s\n' "$drain_output"

second_seed_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  python -m app.utils.project_platform_references --seed-snapshot)"
printf '%s\n' "$second_seed_output"
printf '%s\n' "$second_seed_output" | grep '"seeded_events": 0' >/dev/null \
  || fail "snapshot seed was not idempotent"

operational_locations_after="$(docker compose -f "$COMPOSE_FILE" exec -T postgres sh -c '
  psql -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB" -tAc "
    SELECT md5(COALESCE(string_agg(value, '\''|'\'' ORDER BY value), '\'''\''))
    FROM (
      SELECT id::text || '\'':'\'' || COALESCE(central_location_id::text, '\'''\'') || '\'':'\'' || COALESCE(central_ready_location_id::text, '\'''\'') AS value FROM brands
      UNION ALL
      SELECT id::text || '\'':'\'' || COALESCE(store_location_id::text, '\'''\'') AS value FROM brand_branches
    ) preserved
  "
')"
[ "$operational_locations_before" = "$operational_locations_after" ] \
  || fail "projector changed Restaurant-owned operational location references"

printf 'Replaying an acknowledged event to prove crash-safe idempotency...\n'
replay_event_id="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc "SELECT id FROM reference_outbox WHERE processed_at IS NOT NULL ORDER BY processed_at LIMIT 1"' | tr -d '[:space:]')"
[ -n "$replay_event_id" ] || fail "no processed event is available for replay"
ledger_count_before="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB" -tAc "SELECT count(*) FROM platform_projection_events"' | tr -d '[:space:]')"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -c "UPDATE reference_outbox SET processed_at = NULL, claimed_at = NULL, available_at = now() WHERE id = '\''$1'\''" >/dev/null' \
  sh "$replay_event_id"
replay_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  python -m app.utils.project_platform_references --once --batch-size 1)"
printf '%s\n' "$replay_output"
printf '%s\n' "$replay_output" | grep '"replayed": 1' >/dev/null \
  || fail "acknowledged event was not treated as an idempotent replay"
ledger_count_after="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$RESTAURANT_POSTGRES_DB" -tAc "SELECT count(*) FROM platform_projection_events"' | tr -d '[:space:]')"
[ "$ledger_count_before" = "$ledger_count_after" ] || fail "replay inserted a duplicate ledger row"

printf 'Injecting a missing-source event to verify sanitized retry state...\n'
FAILURE_EVENT_ID="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc "SELECT gen_random_uuid()"' | tr -d '[:space:]')"
missing_aggregate_id="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc "SELECT gen_random_uuid()"' | tr -d '[:space:]')"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -c "
    INSERT INTO reference_outbox (id, event_type, aggregate_type, aggregate_id, schema_version)
    VALUES ('\''$1'\'', '\''platform.reference.changed.v1'\'', '\''company'\'', '\''$2'\'', 1)
  " >/dev/null' sh "$FAILURE_EVENT_ID" "$missing_aggregate_id"
set +e
failure_output="$(docker compose -f "$COMPOSE_FILE" run --rm --no-deps backend \
  python -m app.utils.project_platform_references --once --batch-size 1 2>&1)"
failure_status=$?
set -e
printf '%s\n' "$failure_output"
[ "$failure_status" -ne 0 ] || fail "missing-source event unexpectedly succeeded"
failure_state="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$PLATFORM_POSTGRES_DB" -tAc "
    SELECT attempt_count || '\'':'\'' || (claimed_at IS NULL)::text || '\'':'\'' || (processed_at IS NULL)::text || '\'':'\'' || last_error
    FROM reference_outbox WHERE id = '\''$1'\''
  "' sh "$FAILURE_EVENT_ID" | tr -d '[:space:]')"
[ "$failure_state" = "1:true:true:app.services.platform_reference_projection.ProjectionSourceMissing" ] \
  || fail "unexpected sanitized retry state: $failure_state"

legacy_head_after="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"' | tr -d '[:space:]')"
[ "$legacy_head_after" = "$legacy_head_before" ] || fail "legacy migration head changed"

cat > "$backup_dir/manifest.txt" <<EOF
scope_id=P1-REFERENCE-PROJECTION-05
rehearsal_status=verified
snapshot_timestamp_utc=$timestamp
legacy_database=$legacy_database
legacy_migration_head=$legacy_head_after
platform_database=$platform_database
platform_migration_head=$platform_head
restaurant_database=$restaurant_database
restaurant_migration_head=$restaurant_head
runtime_system_of_record=legacy
snapshot_seed_idempotent=true
projection_parity=true
crash_replay_idempotent=true
sanitized_failure_retry=true
operational_location_fields_preserved=true
contents=platform-before.dump restaurant-before.dump manifest.txt
EOF

cleanup
FAILURE_EVENT_ID=""
printf 'Reference projection rehearsal passed: %s\n' "$backup_dir"
