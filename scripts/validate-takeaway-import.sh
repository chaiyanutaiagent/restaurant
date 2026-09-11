#!/bin/sh
set -eu

BUNDLE_INPUT="${1:-}"
if [ -z "$BUNDLE_INPUT" ] || [ ! -d "$BUNDLE_INPUT" ]; then
  printf 'Usage: %s <takeaway-import-bundle-directory>\n' "$0" >&2
  exit 2
fi

BUNDLE_DIR="$(cd "$BUNDLE_INPUT" && pwd -P)"

docker compose run --rm --no-deps \
  -v "$BUNDLE_DIR:/bundle:ro" \
  backend python -m app.cli.validate_takeaway_import /bundle
