#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
TEMPLATE_FILE="nginx/conf.d/default.prod.https.template.conf"
RENDERED_FILE="nginx/conf.d/default.prod.https.conf"
LETSENCRYPT_HOST_PATH="${LETSENCRYPT_HOST_PATH:-/etc/letsencrypt}"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

value_of() {
  key="$1"
  sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" \
    | tail -n 1 \
    | sed 's/[[:space:]]*$//' \
    | sed 's/^"//; s/"$//; s/^'\''//; s/'\''$//'
}

escape_sed_replacement() {
  printf '%s' "$1" | sed 's/[\/&]/\\&/g'
}

printf 'Validating production environment: %s\n' "$ENV_FILE"
scripts/check-production-env.sh "$ENV_FILE"

SERVER_NAME="$(value_of SERVER_NAME)"
case "$SERVER_NAME" in
  ""|localhost|*.localhost|example.com|*.example.com|placeholder|*placeholder*|*change_me*|*REPLACE_WITH*|*replace_with*)
    fail "SERVER_NAME must be a real production hostname before enabling HTTPS"
    ;;
esac
case "$SERVER_NAME" in
  http://*|https://*|*/*)
    fail "SERVER_NAME must be a hostname only, without scheme or path"
    ;;
esac

FULLCHAIN_FILE="${LETSENCRYPT_HOST_PATH%/}/live/$SERVER_NAME/fullchain.pem"
PRIVKEY_FILE="${LETSENCRYPT_HOST_PATH%/}/live/$SERVER_NAME/privkey.pem"

if [ ! -f "$FULLCHAIN_FILE" ]; then
  fail "certificate file not found: $FULLCHAIN_FILE"
fi
if [ ! -f "$PRIVKEY_FILE" ]; then
  fail "private key file not found: $PRIVKEY_FILE"
fi

if [ ! -f "$TEMPLATE_FILE" ]; then
  fail "nginx HTTPS template not found: $TEMPLATE_FILE"
fi

printf 'Rendering HTTPS nginx config for %s.\n' "$SERVER_NAME"
escaped_server_name="$(escape_sed_replacement "$SERVER_NAME")"
sed "s/\${SERVER_NAME}/$escaped_server_name/g" "$TEMPLATE_FILE" > "$RENDERED_FILE"

export PRODUCTION_ENV_FILE="$ENV_FILE"
export NGINX_PROD_CONF="default.prod.https.conf"
export LETSENCRYPT_HOST_PATH="$LETSENCRYPT_HOST_PATH"

printf 'Validating production compose configuration: %s\n' "$COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" config >/dev/null

printf 'Building nginx image with HTTPS config.\n'
docker compose -f "$COMPOSE_FILE" build nginx

printf 'Testing nginx configuration in a one-off container.\n'
docker compose -f "$COMPOSE_FILE" run --rm --no-deps nginx nginx -t

if docker compose -f "$COMPOSE_FILE" ps -q nginx >/dev/null 2>&1 \
  && [ -n "$(docker compose -f "$COMPOSE_FILE" ps -q nginx 2>/dev/null)" ]; then
  printf 'Recreating nginx with HTTPS config.\n'
  docker compose -f "$COMPOSE_FILE" up -d --no-deps nginx
  docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -t
  docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -s reload
else
  printf 'nginx is not running; start the production stack to use HTTPS.\n'
fi

cat <<EOF

HTTPS activation prepared for $SERVER_NAME.

Next verification commands:
  curl -I https://$SERVER_NAME/health
  curl https://$SERVER_NAME/health/ready
  PRODUCTION_STATUS_BASE_URL=https://$SERVER_NAME ./scripts/check-production-status.sh

No certificate or private key contents were copied into the repository.
EOF
