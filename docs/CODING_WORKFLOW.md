# CODING WORKFLOW — Receipt Bot (strict, repeatable)

Use this every time you change `/opt/Telegram-Receipt-Analysis-Assistant`.
Goal: same architecture, same names, same behavior across runs.

Companion files:
- `docs/PRODUCT_SPEC.md` — product law
- `AGENTS.md` — coding constitution (auto-loaded by Hermes in this cwd)
- `.hermes.md` — short Hermes hard rules

---

## Phase 0 — Orient (mandatory before any edit)

1. Read `docs/PRODUCT_SPEC.md` end-to-end.
2. Read `AGENTS.md`.
3. Map the change to **exactly one** layer:
   - `bot/` transport only
   - `services/` orchestration
   - `llm/` model I/O + OAuth
   - `sheets/` Excel I/O
   - `notify/` email
   - `db.py` session/idempotency
   - `models.py` schema
   - `config.py` settings
4. If the change touches Excel columns, stop and update
   `headers.py` + `ExpenseRow.to_excel_row` + tests + PRODUCT_SPEC together.

Done when: you can state layer + files + user-visible behavior in one sentence.

---

## Phase 1 — Design gates (must answer yes/no)

| Gate | Question |
|------|----------|
| G1 | Does this preserve the image vs text decision tree? |
| G2 | Does extraction still emit only allowed categories? |
| G3 | Does CFO email still fire only when `Total > threshold`? |
| G4 | Is Excel column order unchanged (or fully migrated)? |
| G5 | Is message idempotency preserved? |
| G6 | Are secrets still only in `.env` / Hermes auth.json? |
| G7 | Do unit tests cover the pure logic you changed? |

If any gate is "no" without an explicit PRODUCT_SPEC update, redesign.

---

## Phase 2 — Implement (strict order)

1. **Models first** if schema changes (`models.py`, `headers.py`).
2. **Store/DB next** (`excel_store.py`, `db.py`).
3. **Service orchestration** (`expense_service.py`) — all business branches live here.
4. **LLM client/prompts** only if extraction/chat contracts change.
5. **Handlers** stay thin: auth check → download → call service → reply.
6. **Config/env.example/README** last if new settings.

### File ownership (do not violate)

| Concern | File |
|---------|------|
| Telegram handlers | `bot/handlers.py` |
| App wiring / polling | `bot/app.py` |
| Business flow | `services/expense_service.py` |
| Grok HTTP | `llm/grok_client.py` |
| Prompts | `llm/prompts.py` |
| Hermes xAI OAuth refresh | `llm/xai_oauth.py` |
| Excel | `sheets/excel_store.py`, `sheets/headers.py` |
| SMTP | `notify/smtp_alert.py` |
| Settings | `config.py` |
| Pydantic models | `models.py` |
| SQLite | `db.py` |

### Coding laws

1. `from __future__ import annotations` in every new module.
2. Type hints on public functions.
3. `logging.getLogger(__name__)` — no `print` in package code.
4. `pathlib.Path` for filesystem paths.
5. Async only at Telegram/IO boundaries already async; do not invent threads.
6. Pydantic v2 for structured data crossing boundaries.
7. Never log tokens, passwords, or full Authorization headers.
8. User-facing edge-case strings stay stable (see PRODUCT_SPEC §8).
9. Categories via `Category` enum / `Category.coerce` only.
10. Excel writes go through `ExcelExpenseStore` + portalocker — no ad-hoc openpyxl in handlers.
11. OAuth refresh must use `xai_oauth.resolve_xai_oauth_runtime_credentials`
    (Hermes-compatible); do not invent a second token store as source of truth.
12. Before editing a live config/unit file under `/etc` or `.env`, backup
    `name.bak-YYYYMMDD`.

---

## Phase 3 — Tests (mandatory)

```bash
cd /opt/Telegram-Receipt-Analysis-Assistant
./scripts/test.sh
```

Rules:
- Pure logic changes require a unit test in `tests/`.
- No network in unit tests (mock httpx / temp paths).
- Excel tests use tmp_path workbooks.
- OAuth unit tests use synthetic JWTs + temp auth.json.
- Do not claim done if pytest is red.

Minimum coverage expectations by change type:

| Change | Required tests |
|--------|----------------|
| Category/date/total parsing | `test_models.py` |
| Excel append/query | `test_excel_store.py` |
| Idempotency/session | `test_db.py` |
| JSON extract parse | `test_grok_extract.py` |
| OAuth skew/read store | `test_xai_oauth.py` |
| New branch in service | add focused test or extract pure helper + test |

---

## Phase 4 — Runtime verification

```bash
sudo systemctl restart receipt-bot   # only if runtime behavior changed
systemctl is-active receipt-bot
journalctl -u receipt-bot -n 50 --no-pager
```

Manual smoke (when relevant):
1. `/start` on Telegram bot
2. Send sample receipt image → confirmation + row in `data/expenses.xlsx`
3. Text query about Food spend
4. If testing CFO path: total > threshold and SMTP configured

---

## Phase 5 — Report format (always)

```
Changed: <paths>
Behavior: <one sentence user impact>
Tests: N passed
Service: active|unchanged|restarted
Risks: <none or list>
```

---

## Rebuild-from-scratch recipe (if tree deleted)

Only if PRODUCT_SPEC still governs:

1. Create package layout exactly as §Architecture in AGENTS.md.
2. Implement models + headers first with full column list.
3. Excel store with lock + ensure_workbook.
4. SQLite idempotency + pending total.
5. Grok client + prompts + xai_oauth.
6. ExpenseService branches (image/text/pending).
7. Thin Telegram handlers + app polling.
8. config from `.env` via pydantic-settings.
9. scripts: setup.sh, run.sh, test.sh.
10. systemd unit User=shanem, ReadWritePaths for `data/` and Hermes home if OAuth.
11. `./scripts/test.sh` green before enable.

Do **not** introduce Google Sheets, FastAPI, Docker, or extra agents unless PRODUCT_SPEC is revised.
