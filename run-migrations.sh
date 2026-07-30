#!/bin/bash
# Run F&B migrations
# ใช้: ./run-migrations.sh
# หรือรัน docker compose up ก่อนแล้วค่อยรัน

set -e

echo "=== F&B Migration Runner ==="
echo ""
echo "Migration chain ใหม่:"
echo "  f1a2b3c4d5e6 (stock_count)"
echo "    → e1f2a3b4c5d6 (fb_settings)"
echo "    → b2c3d4e5f6a7 (recipes)"
echo "    → c3d4e5f6a7b8 (dining)"
echo "    → d4e5f6a7b8c9 (qs_qr_token)"
echo ""

# ถ้า backend container รันอยู่
if docker compose ps | grep -q "backend.*running"; then
  echo "✅ พบ backend container — รัน migration..."
  docker compose exec backend alembic upgrade head
else
  echo "⚠️  Backend ยังไม่รัน"
  echo ""
  echo "วิธีรัน:"
  echo "  1. cd restaurant"
  echo "  2. docker compose up -d"
  echo "  3. docker compose exec backend alembic upgrade head"
  echo ""
  echo "หรือรันตรง (ถ้ามี venv):"
  echo "  cd backend && alembic upgrade head"
fi
