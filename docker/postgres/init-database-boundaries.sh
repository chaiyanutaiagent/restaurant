#!/bin/sh
set -eu

validate_database_name() {
  case "$1" in
    ""|*[!A-Za-z0-9_]*)
      printf 'Invalid PostgreSQL database name: %s\n' "$1" >&2
      exit 1
      ;;
  esac
}

create_database_if_missing() {
  database_name="$1"
  validate_database_name "$database_name"
  if ! psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -tAc "SELECT 1 FROM pg_database WHERE datname = '$database_name'" | grep -q 1; then
    createdb --username "$POSTGRES_USER" "$database_name"
  fi
}

create_database_if_missing "${PLATFORM_POSTGRES_DB:-restaurant_platform_core_db}"
create_database_if_missing "${RESTAURANT_POSTGRES_DB:-restaurant_ops_db}"
