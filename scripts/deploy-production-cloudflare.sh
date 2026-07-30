#!/bin/sh
set -eu

ENV_FILE="${1:-.env.production}"
TUNNEL_TOKEN_FILE="${CLOUDFLARE_TUNNEL_TOKEN_FILE:-.secrets/cloudflare-tunnel-token}"

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

if [ ! -f "$ENV_FILE" ]; then
  fail "env file not found: $ENV_FILE"
fi

if [ ! -s "$TUNNEL_TOKEN_FILE" ]; then
  fail "Cloudflare tunnel token file is missing or empty: $TUNNEL_TOKEN_FILE"
fi

server_name="$(value_of SERVER_NAME)"
case "$server_name" in
  ""|localhost|*.localhost|*.example.com|*://*|*/*)
    fail "SERVER_NAME must be the real hostname assigned to this deployment"
    ;;
esac

public_base_url="$(value_of PUBLIC_BASE_URL)"
if [ "$public_base_url" != "https://$server_name" ]; then
  fail "PUBLIC_BASE_URL must be https://$server_name"
fi

cors_origins="$(value_of CORS_ORIGINS)"
case "$cors_origins" in
  *"https://$server_name"*"https://localhost"*|*"https://localhost"*"https://$server_name"*)
    ;;
  *)
    fail "CORS_ORIGINS must include https://$server_name and https://localhost"
    ;;
esac

export COMPOSE_PROFILES=cloudflare
export NGINX_BIND_ADDRESS=127.0.0.1
export NGINX_PROD_CONF=default.prod.cloudflare.conf
export CLOUDFLARE_TUNNEL_TOKEN_FILE="$TUNNEL_TOKEN_FILE"

exec scripts/deploy-production.sh "$ENV_FILE"
