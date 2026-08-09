#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"
ERRORS=0

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  ERRORS=$((ERRORS + 1))
}

value_of() {
  key="$1"
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" \
    | tail -n 1 \
    | sed 's/[[:space:]]*$//' \
    | sed 's/^"//; s/"$//; s/^'\''//; s/'\''$//'
}

has_placeholder() {
  value="$1"
  printf '%s' "$value" | grep -Eiq 'change_me|changeme|placeholder|replace_with|REPLACE_WITH|example\.com|enter_secure_password_here|secure_random|your_|todo'
}

check_required() {
  key="$1"
  value="$(value_of "$key")"
  if [ -z "$value" ]; then
    fail "$key is required"
    return
  fi
  if has_placeholder "$value"; then
    fail "$key still contains a placeholder value"
  fi
}

if [ ! -f "$ENV_FILE" ]; then
  fail "env file not found: $ENV_FILE"
  printf 'Production env validation failed with %s error(s).\n' "$ERRORS" >&2
  exit 1
fi

REQUIRED_VARS="
SERVER_NAME
PUBLIC_BASE_URL
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST
POSTGRES_PORT
DATABASE_URL
REDIS_URL
SECRET_KEY
DEFAULT_ADMIN_PASSWORD
ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS
ENVIRONMENT
CORS_ORIGINS
APP_NAME
APP_VERSION
ENABLE_API_DOCS
CELERY_BROKER_URL
CELERY_RESULT_BACKEND
UPLOAD_DIR
MAX_UPLOAD_SIZE_MB
ALLOWED_UPLOAD_EXTENSIONS
ALLOWED_UPLOAD_MIME_TYPES
SAAS_PUBLIC_BASE_URL
SAAS_EMAIL_DELIVERY_MODE
SAAS_SMTP_HOST
SAAS_SMTP_PORT
SAAS_SMTP_FROM_EMAIL
SAAS_SMTP_USE_TLS
SAAS_SMTP_START_TLS
"

for key in $REQUIRED_VARS; do
  check_required "$key"
done

DEBUG_VALUE="$(value_of DEBUG | tr '[:upper:]' '[:lower:]')"
if [ "$DEBUG_VALUE" = "true" ]; then
  fail "DEBUG must not be true in production"
fi

ENVIRONMENT_VALUE="$(value_of ENVIRONMENT)"
if [ "$ENVIRONMENT_VALUE" != "production" ]; then
  fail "ENVIRONMENT must be production"
fi

SECRET_KEY_VALUE="$(value_of SECRET_KEY)"
if [ "${#SECRET_KEY_VALUE}" -lt 32 ]; then
  fail "SECRET_KEY must be at least 32 characters"
fi

POSTGRES_PASSWORD_VALUE="$(value_of POSTGRES_PASSWORD)"
case "$(printf '%s' "$POSTGRES_PASSWORD_VALUE" | tr '[:upper:]' '[:lower:]')" in
  ""|password|postgres|admin|root|secret|changeme|change_me|change_me_in_production|enter_secure_password_here)
    fail "POSTGRES_PASSWORD is weak or still a default"
    ;;
esac
if [ "${#POSTGRES_PASSWORD_VALUE}" -lt 16 ]; then
  fail "POSTGRES_PASSWORD must be at least 16 characters"
fi

DEFAULT_ADMIN_PASSWORD_VALUE="$(value_of DEFAULT_ADMIN_PASSWORD)"
case "$(printf '%s' "$DEFAULT_ADMIN_PASSWORD_VALUE" | tr '[:upper:]' '[:lower:]')" in
  ""|password|admin|administrator|root|secret|changeme|change_me|change_me_in_production|default_admin|default_admin_password)
    fail "DEFAULT_ADMIN_PASSWORD is weak or still a default"
    ;;
esac
if [ "${#DEFAULT_ADMIN_PASSWORD_VALUE}" -lt 16 ]; then
  fail "DEFAULT_ADMIN_PASSWORD must be at least 16 characters"
fi

CORS_ORIGINS_VALUE="$(value_of CORS_ORIGINS)"
if printf '%s' "$CORS_ORIGINS_VALUE" | grep -Eq '(^|[^[:alnum:]])\*([^[:alnum:]]|$)'; then
  fail "CORS_ORIGINS must not allow wildcard origins"
fi

PUBLIC_BASE_URL_VALUE="$(value_of PUBLIC_BASE_URL)"
ALLOW_HTTP_PUBLIC_BASE_URL_FOR_PILOT_VALUE="$(value_of ALLOW_HTTP_PUBLIC_BASE_URL_FOR_PILOT | tr '[:upper:]' '[:lower:]')"
case "$PUBLIC_BASE_URL_VALUE" in
  http://*)
    if [ "$ALLOW_HTTP_PUBLIC_BASE_URL_FOR_PILOT_VALUE" = "true" ]; then
      printf 'WARNING: PUBLIC_BASE_URL is using http:// because ALLOW_HTTP_PUBLIC_BASE_URL_FOR_PILOT=true. Remove this temporary override after domain and SSL setup.\n' >&2
    else
      fail "PUBLIC_BASE_URL should use https:// for production"
    fi
    ;;
esac

SAAS_PUBLIC_BASE_URL_VALUE="$(value_of SAAS_PUBLIC_BASE_URL)"
case "$SAAS_PUBLIC_BASE_URL_VALUE" in
  https://*)
    ;;
  *)
    fail "SAAS_PUBLIC_BASE_URL must use https:// in production"
    ;;
esac

SAAS_EMAIL_DELIVERY_MODE_VALUE="$(value_of SAAS_EMAIL_DELIVERY_MODE | tr '[:upper:]' '[:lower:]')"
if [ "$SAAS_EMAIL_DELIVERY_MODE_VALUE" != "smtp" ]; then
  fail "SAAS_EMAIL_DELIVERY_MODE must be smtp in production"
fi

SAAS_SMTP_PORT_VALUE="$(value_of SAAS_SMTP_PORT)"
if ! printf '%s' "$SAAS_SMTP_PORT_VALUE" | grep -Eq '^[0-9]+$'; then
  fail "SAAS_SMTP_PORT must be an integer from 1 to 65535"
elif [ "$SAAS_SMTP_PORT_VALUE" -lt 1 ] || [ "$SAAS_SMTP_PORT_VALUE" -gt 65535 ]; then
  fail "SAAS_SMTP_PORT must be an integer from 1 to 65535"
fi

SAAS_SMTP_FROM_EMAIL_VALUE="$(value_of SAAS_SMTP_FROM_EMAIL)"
case "$SAAS_SMTP_FROM_EMAIL_VALUE" in
  *@*.*)
    ;;
  *)
    fail "SAAS_SMTP_FROM_EMAIL must be an email address"
    ;;
esac

SAAS_SMTP_USE_TLS_VALUE="$(value_of SAAS_SMTP_USE_TLS | tr '[:upper:]' '[:lower:]')"
SAAS_SMTP_START_TLS_VALUE="$(value_of SAAS_SMTP_START_TLS | tr '[:upper:]' '[:lower:]')"
for value in "$SAAS_SMTP_USE_TLS_VALUE" "$SAAS_SMTP_START_TLS_VALUE"; do
  case "$value" in
    true|false)
      ;;
    *)
      fail "SAAS_SMTP_USE_TLS and SAAS_SMTP_START_TLS must be true or false"
      break
      ;;
  esac
done
if [ "$SAAS_SMTP_USE_TLS_VALUE" = "true" ] && [ "$SAAS_SMTP_START_TLS_VALUE" = "true" ]; then
  fail "SAAS_SMTP_USE_TLS and SAAS_SMTP_START_TLS must not both be true"
fi

SERVER_NAME_VALUE="$(value_of SERVER_NAME)"
if printf '%s' "$SERVER_NAME_VALUE" | grep -Eq 'https?://|/'; then
  fail "SERVER_NAME must be a hostname only, without scheme or path"
fi

ENABLE_API_DOCS_VALUE="$(value_of ENABLE_API_DOCS | tr '[:upper:]' '[:lower:]')"
case "$ENABLE_API_DOCS_VALUE" in
  true|false)
    ;;
  *)
    fail "ENABLE_API_DOCS must be true or false"
    ;;
esac

if find . \
  -path './.git' -prune -o \
  -type f \( -name '*.pem' -o -name '*.key' -o -name '*.crt' \) \
  -print | grep -q .; then
  fail "certificate or private key files were found inside the repository"
fi

if [ "$ERRORS" -ne 0 ]; then
  printf 'Production env validation failed with %s error(s).\n' "$ERRORS" >&2
  exit 1
fi

printf 'Production env validation passed for %s.\n' "$ENV_FILE"
