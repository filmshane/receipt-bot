# PRODUCT SPEC — Telegram Receipt Analysis Assistant (FROZEN)

Status: **canonical product requirements**. Code must implement this.
Location: `/opt/Telegram-Receipt-Analysis-Assistant`
Package: `receipt-bot` (`src/receipt_bot/`)

When product intent conflicts with convenience, **this file wins**.
When this file conflicts with live column headers / env names already shipped,
**shipped schema wins** and this file must be updated in the same change.

---

## 1. Overview

Automates expense tracking by processing receipt/invoice images via Telegram,
extracting data with Grok vision, logging to a local Excel workbook, and
alerting the CFO for high-value transactions.

| Dimension | Value |
|-----------|--------|
| Type | Single agent / single process bot |
| Model | Grok vision/chat (`XAI_MODEL`, default `grok-4-1-fast`) |
| Input | Telegram text + images |
| Output | Telegram text + Excel rows + optional CFO email |
| Storage | Local `.xlsx` (not Google Sheets) + SQLite session/idempotency |
| Email | Gmail SMTP + App Password (not Workspace API) |

## 2. Users and triggers

- Users: employees (Telegram), CFO (email recipient)
- Frequency: ad-hoc per receipt
- Trigger: new Telegram message (long polling)

## 3. Tools (fixed map)

| Tool | Purpose | Trigger |
|------|---------|---------|
| Grok vision | Extract receipt fields from image | User sends photo/image document |
| Excel store | Append rows; query for Q&A | After extract; user asks spend questions |
| SMTP email | High-value alert | `Total > EXPENSE_THRESHOLD` (default 500) |
| Telegram | UX + session | Every message |
| SQLite | Session continuity + message idempotency | Every handled message |

## 4. Features (must preserve)

### 4.1 Receipt/invoice extraction
- Input: image of receipt/invoice
- Extract: vendor, date, currency, total, tax, category, notes/items summary, confidence
- Categories **exactly**: `Travel` | `Food` | `Equipment` | `Other`

### 4.2 Excel logging
- Insert one row per accepted receipt
- Workbook path: `EXPENSE_XLSX_PATH` (default `./data/expenses.xlsx`)
- Sheet: `EXPENSE_SHEET_NAME` (default `Expenses`)

### 4.3 CFO alerting
- Condition: `Total > EXPENSE_THRESHOLD` (default `500`)
- Action: Gmail SMTP email to `CFO_EMAIL`
- Content: vendor, date, total, tax, category, notes, telegram user, message id, confidence, needs_review
- Record `CFOEmailSentAt` on the row when send succeeds

### 4.4 Interactive chat and sheet query
- Continuous conversation per Telegram chat (SQLite pending/session state)
- User can ask questions like "How much did I spend on Food last month?"
- Agent uses Excel query tools; **must not invent numbers**

## 5. User flow (decision tree)

```
message received
├─ unauthorized user? → "Unauthorized."
├─ image (photo or image/* document)
│  ├─ already processed (chat_id, message_id)? → "Already logged this message."
│  ├─ Grok extract
│  ├─ not a receipt → fixed copy (see Edge Cases)
│  ├─ unreadable / no total + low confidence → fixed copy or prompt for total
│  ├─ append Excel row
│  ├─ if Total > threshold → SMTP CFO (best-effort; log failures)
│  └─ confirm to user
└─ text
   ├─ pending missing-total state? → parse amount, complete row, maybe CFO email
   └─ else Grok chat + expense tools → answer from Excel only
```

## 6. Excel columns (immutable order and names)

Defined in `src/receipt_bot/sheets/headers.py` — **do not rename or reorder**
without a migration plan and test updates:

```
TelegramUserId, TelegramUsername, ReceiptFileId, Vendor, ExpenseDate,
Currency, Total, Tax, Category, Notes, Confidence, NeedsReview,
MessageId, Over500, CFOEmailSentAt
```

Boolean cells stored as `"TRUE"` / `"FALSE"` strings.
`ExpenseDate` is `YYYY-MM-DD`.
`Over500` is derived: `Total > threshold`.

## 7. Rules and constraints

1. Track Telegram chat/session for continuous conversation (SQLite).
2. CFO email and SMTP credentials are env-configured; never hardcode secrets.
3. Excel path and sheet name are env-configured.
4. Categories only: Travel, Food, Equipment, Other.
5. Message idempotency: same `(chat_id, message_id)` must not double-log.
6. xAI auth: prefer Hermes OAuth refresh (`xai_oauth.py`) matching Hermes;
   static `XAI_API_KEY` is fallback only.
7. No Google Sheets API. Local openpyxl + file lock only.
8. No destructive mass-delete of data files.

## 8. Edge cases (fixed user-facing copy)

| Case | Response requirement |
|------|----------------------|
| Unclear image | Include: `Could not extract data. Please send a clearer image.` |
| Non-receipt | Exactly or include: `This doesn't appear to be a receipt or invoice. Please send a relevant image.` |
| Missing total | Prompt user to reply with the total amount; hold pending state |
| Sheet/IO error | Inform temporary issue; advise retry |
| SMTP failure | Still keep Excel row; do not crash bot; surface brief note if useful |
| Grok/API error | Tell user temporary model error; do not fake extraction |

## 9. Non-goals

- Multi-agent orchestration
- Web UI
- Google Sheets / Drive
- Payment processing
- Automatic receipt photography
- Changing category vocabulary without explicit product change
