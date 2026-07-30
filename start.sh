#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HTTP_PORT="${RESTAURANT_HTTP_PORT:-8081}"
API_PORT="${RESTAURANT_API_PORT:-8001}"

echo "================================================"
echo "  Restaurant POS — Starting..."
echo "================================================"

if ! docker info > /dev/null 2>&1; then
  echo "❌ Docker is not running. Please start Docker Desktop and try again."
  exit 1
fi

cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
  echo "⚙️  Creating .env from .env.example..."
  cp .env.example .env
fi

for PORT in "$HTTP_PORT" "$API_PORT"; do
  if lsof -i ":$PORT" -sTCP:LISTEN > /dev/null 2>&1 \
    && ! docker compose ps --format json 2>/dev/null | grep -q "\"$PORT\""; then
    echo "❌ Port $PORT is already used by another application."
    echo "   Change RESTAURANT_HTTP_PORT or RESTAURANT_API_PORT and try again."
    exit 1
  fi
done

echo "🐳 Building and starting this project's containers..."
docker compose up --build -d

echo "🗄️  Running database migrations..."
docker compose run --rm backend alembic upgrade heads

echo "⏳ Waiting for services..."
READY=false
for _ in {1..45}; do
  if curl -fsS "http://localhost:${HTTP_PORT}/health" 2>/dev/null | grep -q '"ok"'; then
    READY=true
    break
  fi
  printf "."
  sleep 2
done
echo

if [ "$READY" = false ]; then
  echo "❌ Services did not become ready."
  docker compose logs --tail=40 backend nginx
  exit 1
fi

echo "================================================"
echo "  ✅ Restaurant POS is ready"
echo "  🌐 App: http://localhost:${HTTP_PORT}"
echo "  🔌 API: http://localhost:${API_PORT}"
echo "  👤 Username: admin"
echo "  🔑 Password: DEFAULT_ADMIN_PASSWORD from local .env"
echo "================================================"
