# AGENTS.md — Telegram Receipt Analysis Assistant

Strict coding constitution for this repository.
Install root: `/opt/Telegram-Receipt-Analysis-Assistant`
Python package: `receipt-bot` under `src/receipt_bot/`

**Primary rebuild/spec document (no code):** `docs/LOGIC_WORKFLOW.md`.
**Before any code change:** read `docs/LOGIC_WORKFLOW.md`, then `docs/PRODUCT_SPEC.md` and `docs/CODING_WORKFLOW.md`.
If instructions conflict: PRODUCT_SPEC > this file > existing code comments > convenience.

---

## Mission

Single Telegram bot that:
1. Accepts receipt/invoice images
2. Extracts fields with Grok vision
3. Appends a row to local Excel
4. Emails CFO when Total > threshold
5. Answers spend questions from Excel (no invented numbers)

---

## Architecture (do not redesign)

```
Telegram (long poll)
  → bot/handlers.py          # thin: auth, download, reply
  → services/expense_service.py  # ALL business branches
       ├─ llm/grok_client.py + prompts.py + xai_oauth.py
       ├─ sheets/excel_store.py + headers.py
       ├─ notify/smtp_alert.py
       └─ db.py              # idempotency + pending + light session
config.py ← .env / RECEIPT_BOT_ENV
models.py ← Category, ExpenseRow, ExtractionResult
```

Stack (fixed unless PRODUCT_SPEC changes):
- Python 3.12+, package in `src/`
- `python-telegram-bot` v21+
- `httpx`, `pydantic` v2, `pydantic-settings`
- `openpyxl` + `portalocker`
- `aiosmtplib` Gmail SMTP
- pytest + pytest-asyncio
- systemd unit `receipt-bot.service`
- **Local Excel only** — never Google Sheets API
- **Hermes-compatible xAI OAuth** in `llm/xai_oauth.py` (default on)

---

## Immutable Excel schema

File: `src/receipt_bot/sheets/headers.py`

Order and names are frozen:

`TelegramUserId, TelegramUsername, ReceiptFileId, Vendor, ExpenseDate, Currency, Total, Tax, Category, Notes, Confidence, NeedsReview, MessageId, Over500, CFOEmailSentAt`

- Booleans as `"TRUE"`/`"FALSE"` strings
- Dates `YYYY-MM-DD`
- `Over500` ⇔ `Total > EXPENSE_THRESHOLD`
- Categories enum only: Travel | Food | Equipment | Other

Any column change = headers + `ExpenseRow.to_excel_row` + PRODUCT_SPEC + tests in one commit-worthy change set.

---

## Decision tree (must remain)

```
message
├─ not allowed → "Unauthorized."
├─ image
│  ├─ db.is_processed → already logged
│  ├─ grok.extract
│  ├─ !is_receipt → non-receipt copy
│  ├─ bad/unclear → clearer-image copy
│  ├─ total missing → pending + ask user for total
│  ├─ store.append + mark processed
│  └─ total > threshold → SMTP CFO; set CFOEmailSentAt on success
└─ text
   ├─ pending total? → complete row (+ CFO if needed)
   └─ grok.chat + expense tools over Excel → answer
```

### Fixed edge-case strings (stable UX)

- Non-receipt: include `This doesn't appear to be a receipt or invoice. Please send a relevant image.`
- Unclear: include `Could not extract data. Please send a clearer image.`

Do not "improve" these strings casually.

---

## Layer rules

| Layer | May | Must not |
|-------|-----|----------|
| `bot/handlers.py` | Auth gate, download bytes, typing, reply | Business rules, openpyxl, SMTP, prompts |
| `services/expense_service.py` | Orchestrate extract/log/alert/query | Telegram API details beyond UserContext |
| `llm/*` | HTTP to xAI, OAuth refresh, prompts | Excel writes, SMTP |
| `sheets/*` | Workbook I/O, filters, sums | Telegram, LLM |
| `notify/*` | SMTP send | Decide whether threshold exceeded |
| `db.py` | processed keys, pending JSON | Excel |
| `config.py` | settings only | side effects at import beyond env load |

---

## Coding standards

1. Every module: `from __future__ import annotations`
2. Public functions typed; prefer Pydantic models at boundaries
3. `logger = logging.getLogger(__name__)` — never `print` in package
4. `pathlib.Path` for paths
5. No secrets in code, git, logs, or tests
6. Backup before editing `.env` or systemd units: `*.bak-YYYYMMDD`
7. No `rm -rf` data dirs; no wiping `data/expenses.xlsx` as "fix"
8. Async: keep existing async style; don't add thread pools without need
9. Idempotency key: `(chat_id, message_id)`
10. Threshold comparisons: use settings `expense_threshold`, not hard-coded 500 in new logic (default may stay 500)
11. Grok extraction JSON keys must match `ExtractionResult`
12. Chat must use tools for numbers; prompts forbid inventing spend data
13. xAI credentials resolution order:
    1. Hermes OAuth via `resolve_xai_oauth_runtime_credentials` when `xai_use_hermes_oauth`
    2. optional `xai_token_file`
    3. static `xai_api_key`
14. OAuth refresh must lock auth store, POST refresh_token grant with Hermes client_id, write rotated tokens back to `~/.hermes/auth.json`
15. On Grok HTTP 401 with OAuth: force refresh once, retry once

---

## Env surface (authoritative keys)

See `.env.example`. Critical:

- `TELEGRAM_BOT_TOKEN`
- `XAI_API_KEY` (fallback)
- `XAI_USE_HERMES_OAUTH` (default true)
- `HERMES_HOME` (default `~/.hermes`)
- `XAI_MODEL` / `XAI_BASE_URL`
- `EXPENSE_XLSX_PATH` / `EXPENSE_SHEET_NAME` / `EXPENSE_THRESHOLD`
- `CFO_EMAIL` / `SMTP_*`
- `ALLOWED_TELEGRAM_USER_IDS` (empty = allow all)
- `DATABASE_PATH` / `LOG_LEVEL`
- `RECEIPT_BOT_ENV` absolute override path

Never commit `.env`.

---

## Commands (always use these)

```bash
cd /opt/Telegram-Receipt-Analysis-Assistant
./scripts/setup.sh          # venv + editable install
./scripts/test.sh           # pytest -q  — MUST be green before done
./scripts/run.sh            # foreground
sudo systemctl restart receipt-bot
systemctl status receipt-bot --no-pager
journalctl -u receipt-bot -n 80 --no-pager
```

Package entry: `.venv/bin/python -m receipt_bot` or console script `receipt-bot`.

---

## Definition of done

A change is done only when **all** are true:

- [ ] PRODUCT_SPEC behavior preserved or PRODUCT_SPEC updated deliberately
- [ ] Layer ownership respected
- [ ] `./scripts/test.sh` exits 0
- [ ] No secrets in diff
- [ ] Excel headers unchanged or fully migrated with tests
- [ ] If runtime code path changed: service restarted and `active`
- [ ] Report uses the Phase 5 format from `docs/CODING_WORKFLOW.md`

---

## Forbidden refactors (unless PRODUCT_SPEC explicitly revised)

- Replacing Excel with Google Sheets / DB-only storage
- Adding FastAPI/Flask web UI as primary interface
- Multi-agent / queue workers for the happy path
- Renaming package from `receipt_bot` / project folder casually
- Changing category set
- Dropping CFO email feature
- Dropping Telegram as primary channel
- Storing OAuth refresh tokens outside Hermes auth.json as a second source of truth
- Weakening idempotency

---

## When regenerating a feature

1. Copy behavior from `expense_service.py` branches, not from memory.
2. Match user-facing strings to PRODUCT_SPEC §8.
3. Match column order to `headers.py`.
4. Match extraction JSON to `prompts.EXTRACTION_SYSTEM`.
5. Add/adjust unit tests before declaring success.
6. Run `./scripts/test.sh`.

---

## Original product intent (summary)

Employees send receipt images on Telegram → Grok extracts Date/Total/Tax/Items/Category → row in spreadsheet → if Total > 500 email CFO → text questions answered from sheet. Session continuity required. Edge cases for unclear/non-receipt/missing total/API errors required.

Full detail: `docs/PRODUCT_SPEC.md`.
