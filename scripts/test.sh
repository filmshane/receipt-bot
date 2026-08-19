#!/usr/bin/env bash
# pytest on Ubuntu / Linux
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Missing .venv. Run: ./scripts/setup.sh" >&2
  exit 1
fi

exec .venv/bin/python -m pytest -q "$@"
