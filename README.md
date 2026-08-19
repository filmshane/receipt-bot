# Telegram Receipt Analysis Assistant

Excel-only expense bot for Telegram. Grok vision extracts receipt fields, rows go to a local `.xlsx`, and totals over the threshold email the CFO via **Gmail SMTP** (App Password — no Google Workspace).

Works on **Windows** and **Ubuntu 24.04** (`/usr/bin/python3`).


## Agent coding workflow (Hermes)

Strict, repeatable rules for coding this bot the same way every time:

| File | Role |
|------|------|
| `docs/LOGIC_WORKFLOW.md` | **Primary** no-code logic workflow + schemas to rebuild the same agent |
| `docs/PRODUCT_SPEC.md` | Frozen product requirements (original agent brief) |
| `docs/CODING_WORKFLOW.md` | Phase 0–5 change process |
| `AGENTS.md` | Coding constitution (auto-loaded when cwd is this project) |
| `.hermes.md` | Short Hermes hard rules |
| Hermes skill `receipt-bot-workflow` | Load when working on this bot from any cwd |

```bash
cd /opt/Telegram-Receipt-Analysis-Assistant
# Hermes in this directory auto-loads AGENTS.md / .hermes.md
hermes chat -q "Fix missing-total pending flow per AGENTS.md"
```

## Features

- Photo / image document → Grok extract → Excel row
- Text Q&A against Excel ("How much did I spend on Food last month?")
- CFO email when `Total > EXPENSE_THRESHOLD` (default 500)
- Session continuity + message idempotency (SQLite)

## Ubuntu 24.04

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip

cd /path/to/Telegram-Receipt-Analysis-Assistant
chmod +x scripts/*.sh
./scripts/setup.sh
nano .env    # fill secrets
./scripts/test.sh
./scripts/run.sh
```

`setup.sh` uses **`/usr/bin/python3`** when present to create `.venv`.

### Optional systemd unit

```ini
# /etc/systemd/system/receipt-bot.service
[Unit]
Description=Telegram Receipt Analysis Assistant
After=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/Telegram-Receipt-Analysis-Assistant
Environment=RECEIPT_BOT_ENV=/opt/Telegram-Receipt-Analysis-Assistant/.env
ExecStart=/opt/Telegram-Receipt-Analysis-Assistant/.venv/bin/python -m receipt_bot
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now receipt-bot
```

## Windows

```powershell
cd $env:USERPROFILE\Documents\Projects\Telegram-Receipt-Analysis-Assistant
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup.ps1
notepad .env
.\scripts\test.ps1
.\scripts\run.ps1
```

## `.env` keys

| Variable | Notes |
|----------|--------|
| `TELEGRAM_BOT_TOKEN` | BotFather — rotate if exposed |
| `XAI_API_KEY` | xAI Grok |
| `XAI_MODEL` | default `grok-4-1-fast` |
| `SMTP_USER` / `SMTP_PASSWORD` | Gmail + **App Password** |
| `SMTP_FROM` | usually same as SMTP_USER |
| `CFO_EMAIL` | alert destination |
| `EXPENSE_XLSX_PATH` | optional; default `./data/expenses.xlsx` |
| `RECEIPT_BOT_ENV` | optional absolute path to env file (systemd) |

### Gmail App Password

1. Enable 2-Step Verification  
2. https://myaccount.google.com/apppasswords  
3. Set `SMTP_PASSWORD`

## Manual run (after setup)

```bash
# Linux
.venv/bin/python -m receipt_bot

# Windows
.venv\Scripts\python.exe -m receipt_bot
```

Package is installed editable (`pip install -e .`) so **PYTHONPATH is not required**.

## Excel columns

TelegramUserId, TelegramUsername, ReceiptFileId, Vendor, ExpenseDate, Currency, Total, Tax, Category, Notes, Confidence, NeedsReview, MessageId, Over500, CFOEmailSentAt

## xAI auth (Hermes OAuth)

By default the bot uses the **same xAI OAuth refresh method as Hermes**:

- Reads `~/.hermes/auth.json` (`providers.xai-oauth`)
- Locks `auth.lock` during refresh
- Proactive JWT refresh (up to 1h early; adaptive for short tokens)
- `POST grant_type=refresh_token` to `https://auth.x.ai/oauth2/token` with Hermes client_id
- Writes rotated access + refresh tokens back to `auth.json` (required — xAI rotates refresh tokens)

Env:
- `XAI_USE_HERMES_OAUTH=true` (default)
- `HERMES_HOME=/home/shanem/.hermes`
- Optional static fallback: `XAI_API_KEY`
- Disable OAuth: `XAI_USE_HERMES_OAUTH=false`

## Security

- Never commit `.env`
- Rotate Telegram token if exposed
- App passwords ≠ account password
