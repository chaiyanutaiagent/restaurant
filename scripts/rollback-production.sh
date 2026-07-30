#!/bin/sh
set -eu

ENV_FILE="${PRODUCTION_ENV_FILE:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
BACKUP_DIR=""
ASSUME_YES=0
APP_ONLY=0
TARGET_RELEASE_VERSION=""
PRODUCTION_IMAGE_MODE="${PRODUCTION_IMAGE_MODE:-build}"

usage() {
  cat <<'EOF'
Usage:
  scripts/rollback-production.sh --app-only [ENV_FILE]
  scripts/rollback-production.sh --release RELEASE_VERSION --app-only [ENV_FILE]
  scripts/rollback-production.sh --data-restore BACKUP_DIR [--yes] [ENV_FILE]

Rollback modes:
  --app-only
      Recreate compose services and run production status checks.

  --release RELEASE_VERSION
      Use a specific immutable app image tag for backend, frontend, and nginx.
      Target images must exist locally in build mode, or be pullable in pull mode.

  --data-restore BACKUP_DIR
      Destructively restore PostgreSQL, uploads, and Redis data by calling
      scripts/restore-production.sh BACKUP_DIR, then start the app and run status checks.

Options:
  --yes
      Pass non-interactive confirmation through to scripts/restore-production.sh.

Environment:
  COMPOSE_FILE defaults to docker-compose.prod.yml.
  PRODUCTION_ENV_FILE defaults to .env.production.
EOF
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  printf 'Run scripts/rollback-production.sh --help for usage.\n' >&2
  exit 1
}

require_executable() {
  script="$1"
  if [ ! -x "$script" ]; then
    fail "$script is missing or not executable"
  fi
}

validate_release_version() {
  version="$1"
  case "$version" in
    ""|*[^A-Za-z0-9._-]*)
      fail "release version may contain only letters, numbers, dot, underscore, and hyphen"
      ;;
  esac
}

require_release_images() {
  version="$1"
  if [ "$PRODUCTION_IMAGE_MODE" = "pull" ]; then
    return
  fi

  for image in "$BACKEND_IMAGE" "$FRONTEND_IMAGE" "$NGINX_IMAGE"; do
    if ! docker image inspect "$image" >/dev/null 2>&1; then
      fail "required rollback image not found locally: $image"
    fi
  done
}

current_service_image() {
  service="$1"
  container_id="$(docker compose -f "$COMPOSE_FILE" ps -a -q "$service" 2>/dev/null || true)"
  if [ -z "$container_id" ]; then
    return 1
  fi
  docker inspect --format '{{.Config.Image}}' "$container_id"
}

configure_current_images() {
  if [ "$PRODUCTION_IMAGE_MODE" = "pull" ]; then
    fail "--release is required for registry pull rollback"
  fi

  BACKEND_IMAGE="${BACKEND_IMAGE:-$(current_service_image backend || true)}"
  FRONTEND_IMAGE="${FRONTEND_IMAGE:-$(current_service_image frontend || true)}"
  NGINX_IMAGE="${NGINX_IMAGE:-$(current_service_image nginx || true)}"

  if [ -z "$BACKEND_IMAGE" ] || [ -z "$FRONTEND_IMAGE" ] || [ -z "$NGINX_IMAGE" ]; then
    fail "current app images could not be detected; rerun with --release RELEASE_VERSION"
  fi

  export BACKEND_IMAGE FRONTEND_IMAGE NGINX_IMAGE
  printf 'Using current backend image: %s\n' "$BACKEND_IMAGE"
  printf 'Using current frontend image: %s\n' "$FRONTEND_IMAGE"
  printf 'Using current nginx image: %s\n' "$NGINX_IMAGE"
}

normalize_registry() {
  printf '%s' "${IMAGE_REGISTRY%/}"
}

normalize_namespace() {
  namespace="$1"
  namespace="${namespace#/}"
  printf '%s' "${namespace%/}"
}

configure_images() {
  version="$1"

  if [ "$PRODUCTION_IMAGE_MODE" != "pull" ] && { [ -n "${IMAGE_REGISTRY:-}" ] || [ -n "${IMAGE_NAMESPACE:-}" ]; }; then
    PRODUCTION_IMAGE_MODE="pull"
  fi

  case "$PRODUCTION_IMAGE_MODE" in
    build)
      BACKEND_IMAGE="${BACKEND_IMAGE:-restaurant-pos-backend:$version}"
      FRONTEND_IMAGE="${FRONTEND_IMAGE:-restaurant-pos-frontend:$version}"
      NGINX_IMAGE="${NGINX_IMAGE:-restaurant-pos-nginx:$version}"
      ;;
    pull)
      if [ -z "${IMAGE_REGISTRY:-}" ]; then
        fail "IMAGE_REGISTRY is required when PRODUCTION_IMAGE_MODE=pull"
      fi
      if [ -z "${IMAGE_NAMESPACE:-}" ]; then
        fail "IMAGE_NAMESPACE is required when PRODUCTION_IMAGE_MODE=pull"
      fi
      registry="$(normalize_registry)"
      namespace="$(normalize_namespace "$IMAGE_NAMESPACE")"
      BACKEND_IMAGE="${BACKEND_IMAGE:-$registry/$namespace/restaurant-pos-backend:$version}"
      FRONTEND_IMAGE="${FRONTEND_IMAGE:-$registry/$namespace/restaurant-pos-frontend:$version}"
      NGINX_IMAGE="${NGINX_IMAGE:-$registry/$namespace/restaurant-pos-nginx:$version}"
      ;;
    *)
      fail "PRODUCTION_IMAGE_MODE must be build or pull"
      ;;
  esac

  export PRODUCTION_IMAGE_MODE BACKEND_IMAGE FRONTEND_IMAGE NGINX_IMAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --app-only)
      APP_ONLY=1
      shift
      ;;
    --release)
      shift
      if [ "$#" -eq 0 ]; then
        fail "--release requires a release version"
      fi
      TARGET_RELEASE_VERSION="$1"
      shift
      ;;
    --data-restore)
      shift
      if [ "$#" -eq 0 ]; then
        fail "--data-restore requires a backup directory"
      fi
      BACKUP_DIR="$1"
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    -*)
      fail "unknown option: $1"
      ;;
    *)
      ENV_FILE="$1"
      shift
      ;;
  esac
done

if [ "$APP_ONLY" -eq 1 ] && [ -n "$BACKUP_DIR" ]; then
  fail "choose either --app-only or --data-restore, not both"
fi

if [ "$APP_ONLY" -ne 1 ] && [ -z "$BACKUP_DIR" ]; then
  fail "rollback mode is required: use --app-only or --data-restore BACKUP_DIR"
fi

require_executable scripts/check-production-env.sh
require_executable scripts/check-production-status.sh
if [ -n "$BACKUP_DIR" ]; then
  require_executable scripts/restore-production.sh
fi

printf 'Validating production environment: %s\n' "$ENV_FILE"
scripts/check-production-env.sh "$ENV_FILE"

export PRODUCTION_ENV_FILE="$ENV_FILE"
if [ -n "$TARGET_RELEASE_VERSION" ]; then
  validate_release_version "$TARGET_RELEASE_VERSION"
  export RELEASE_VERSION="$TARGET_RELEASE_VERSION"
  configure_images "$TARGET_RELEASE_VERSION"
  printf 'Using rollback release version: %s\n' "$TARGET_RELEASE_VERSION"
  printf 'Using image mode: %s\n' "$PRODUCTION_IMAGE_MODE"
  require_release_images "$TARGET_RELEASE_VERSION"
elif [ "$PRODUCTION_IMAGE_MODE" = "pull" ] || [ -n "${IMAGE_REGISTRY:-}" ] || [ -n "${IMAGE_NAMESPACE:-}" ]; then
  fail "--release is required for registry pull rollback"
fi

printf 'Validating production compose configuration: %s\n' "$COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" config >/dev/null

if [ -z "$TARGET_RELEASE_VERSION" ]; then
  configure_current_images
fi

if [ -n "$BACKUP_DIR" ]; then
  if [ ! -d "$BACKUP_DIR" ]; then
    fail "backup directory not found: $BACKUP_DIR"
  fi

  printf '%s\n' 'WARNING: data restore rollback is destructive.'
  printf '%s\n' 'PostgreSQL, uploads, and Redis data will be restored from the selected backup.'

  if [ "$ASSUME_YES" -eq 1 ]; then
    scripts/restore-production.sh --yes "$BACKUP_DIR"
  else
    scripts/restore-production.sh "$BACKUP_DIR"
  fi
else
  printf '%s\n' 'App-only rollback selected.'
  if [ -n "$TARGET_RELEASE_VERSION" ]; then
    printf 'Recreating services with release images tagged: %s\n' "$TARGET_RELEASE_VERSION"
  else
    printf '%s\n' 'No --release supplied; recreating services with the current RELEASE_VERSION/default image tag.'
  fi
fi

if [ "$PRODUCTION_IMAGE_MODE" = "pull" ]; then
  printf 'Pulling rollback images from registry.\n'
  docker compose -f "$COMPOSE_FILE" pull backend frontend nginx
fi

printf 'Starting production application stack.\n'
docker compose -f "$COMPOSE_FILE" up -d --no-build

printf 'Checking production status after rollback.\n'
scripts/check-production-status.sh

printf '\nProduction rollback flow completed.\n'
