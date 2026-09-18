#!/usr/bin/env bash
# Idempotent bootstrap for the DELEVA development environment.
#
# Prepares:
#   - a Python virtualenv (.venv) with the backend dependencies (proof/requirements.txt)
#   - the frontend node_modules (web/)
#
# Safe to run repeatedly: it refreshes dependencies in place and never starts a
# long-running process.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Python's stdlib venv module requires the python3-venv system package on
# Debian/Ubuntu. Install it only if it is missing.
if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "==> Installing python3-venv"
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

echo "==> Creating/refreshing Python virtualenv (.venv)"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip --quiet
./.venv/bin/pip install -r proof/requirements.txt --quiet

echo "==> Installing frontend dependencies (web/)"
cd web
npm install

echo "==> DELEVA environment ready."
