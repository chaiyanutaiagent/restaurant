#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
TMP_BASE="${TMPDIR:-/tmp}"
if [ -d /private/tmp ]; then
  TMP_BASE="/private/tmp"
fi
VENV_DIR="${BACKEND_REGRESSION_VENV:-$TMP_BASE/restaurant-pos-backend-regression-venv}"
PYCACHE_DIR="${PYCACHE_DIR:-$TMP_BASE/restaurant-pos-backend-regression-pycache}"

export PYTHONPYCACHEPREFIX="$PYCACHE_DIR"

python_ok() {
  python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

run_with_docker() {
  command -v docker >/dev/null 2>&1 || {
    printf 'ERROR: Python 3.10+ is required, and Docker was not found for fallback.\n' >&2
    exit 1
  }

  DOCKER_SRC="$TMP_BASE/restaurant-pos-backend-regression-src"
  rm -rf "$DOCKER_SRC"
  mkdir -p "$DOCKER_SRC"
  cp -R "$BACKEND_DIR" "$DOCKER_SRC/backend"
  cp "$ROOT_DIR/.env.example" "$DOCKER_SRC/backend/.env"

  printf 'Local python3 is older than 3.10; running backend regression checks in python:3.11-slim.\n'
  docker run --rm \
    -v "$DOCKER_SRC/backend:/backend:ro" \
    -w /backend \
    python:3.11-slim \
    sh -c '
      set -eu
      apt-get update >/dev/null
      apt-get install -y --no-install-recommends libmagic1 libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info >/dev/null
      rm -rf /var/lib/apt/lists/*
      python -m venv /tmp/restaurant-pos-regression-venv
      /tmp/restaurant-pos-regression-venv/bin/python -m pip install --upgrade pip >/dev/null
      /tmp/restaurant-pos-regression-venv/bin/python -m pip install -r requirements.txt >/dev/null
      export PYTHONPYCACHEPREFIX=/tmp/restaurant-pos-pycache
      /tmp/restaurant-pos-regression-venv/bin/python -m compileall -q app tests
      /tmp/restaurant-pos-regression-venv/bin/python -m unittest discover -s tests -p "test_*.py"
    '
  rm -rf "$DOCKER_SRC"
}

if ! python_ok; then
  run_with_docker
  printf 'Backend regression checks passed.\n'
  exit 0
fi

if [ ! -x "$VENV_DIR/bin/python" ]; then
  printf 'Creating backend regression virtual environment: %s\n' "$VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

printf 'Installing backend regression dependencies.\n'
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install -r "$BACKEND_DIR/requirements.txt" >/dev/null

printf 'Running backend Python compile check.\n'
"$VENV_DIR/bin/python" -m compileall -q "$BACKEND_DIR/app" "$BACKEND_DIR/tests"

printf 'Running focused backend regression tests.\n'
(
  cd "$BACKEND_DIR"
  "$VENV_DIR/bin/python" -m unittest discover -s tests -p 'test_*.py'
)

printf 'Backend regression checks passed.\n'
