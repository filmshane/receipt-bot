#!/usr/bin/env bash
# Optional manual refresh using receipt-bot's Hermes-compatible OAuth module.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export HERMES_HOME="${HERMES_HOME:-/home/shanem/.hermes}"
exec "$ROOT/.venv/bin/python" - <<'PY'
from receipt_bot.llm.xai_oauth import resolve_xai_oauth_runtime_credentials
c = resolve_xai_oauth_runtime_credentials(force_refresh=True, refresh_if_expiring=True)
print("ok source=", c.get("source"), "key_len=", len(c.get("api_key") or ""))
PY
