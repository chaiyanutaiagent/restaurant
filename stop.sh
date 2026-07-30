#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🛑 Stopping this Restaurant POS stack..."
cd "$SCRIPT_DIR"
docker compose down
echo "✅ Restaurant POS stopped."
