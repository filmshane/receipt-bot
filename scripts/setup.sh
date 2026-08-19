#!/usr/bin/env bash
# Setup Telegram Receipt Analysis Assistant on Ubuntu 24.04 (+ other Linux).
# Uses /usr/bin/python3 explicitly when present.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "Project root: $ROOT"

if [[ -x /usr/bin/python3 ]]; then
  PY=/usr/bin/python3
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "ERROR: python3 not found. On Ubuntu 24.04:" >&2
  echo "  sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip" >&2
  exit 1
fi

echo "Python: $PY ($("$PY" --version 2>&1))"

# Ensure venv module
if ! "$PY" -c "import venv" 2>/dev/null; then
  echo "ERROR: python3-venv missing. Run:" >&2
  echo "  sudo apt-get install -y python3-venv python3-pip" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Creating .venv ..."
  "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install -e ".[dev]"

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit secrets before run."
  fi
else
  echo ".env already exists (left unchanged)."
fi

mkdir -p data
chmod +x scripts/*.sh 2>/dev/null || true

echo ""
echo "Setup OK. Next:"
echo "  1. nano .env   # TELEGRAM_BOT_TOKEN XAI_API_KEY SMTP_PASSWORD CFO_EMAIL"
echo "  2. ./scripts/run.sh"
echo "  3. ./scripts/test.sh"
