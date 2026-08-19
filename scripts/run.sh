#!/usr/bin/env bash
# Run receipt-bot on Ubuntu 24.04 / Linux (long polling).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run: ./scripts/setup.sh" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "Missing .env — copy .env.example and fill secrets." >&2
  exit 1
fi

# Prefer venv interpreter (created from /usr/bin/python3 on Ubuntu)
exec .venv/bin/python -m receipt_bot "$@"
