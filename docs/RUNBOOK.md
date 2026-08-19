# Runbook — Telegram Receipt Analysis Assistant

## Platforms

| OS | Setup | Run | Test |
|----|-------|-----|------|
| Ubuntu 24.04 | `./scripts/setup.sh` | `./scripts/run.sh` | `./scripts/test.sh` |
| Windows | `.\scripts\setup.ps1` | `.\scripts\run.ps1` | `.\scripts\test.ps1` |

Ubuntu setup prefers **`/usr/bin/python3`**.

## Prerequisites (Ubuntu)

```bash
sudo apt-get install -y python3 python3-venv python3-pip
```

Outbound HTTPS required: `api.telegram.org`, `api.x.ai`, `smtp.gmail.com:587`.

## Data

- Excel: `data/expenses.xlsx` (or `EXPENSE_XLSX_PATH`)
- SQLite: `data/bot.db`
- Backup Excel regularly

## CFO email

- Use Gmail **App Password**, not the normal password
- `SMTP_HOST=smtp.gmail.com` `SMTP_PORT=587`

## Env file override

```bash
export RECEIPT_BOT_ENV=/etc/receipt-bot.env
.venv/bin/python -m receipt_bot
```
