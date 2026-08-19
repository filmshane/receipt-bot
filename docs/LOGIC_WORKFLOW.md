# Logic Workflow Document
## Telegram Receipt Analysis Assistant — Repeatable Build Spec

**Document type:** Logic workflow + product schema (no implementation code)  
**Purpose:** Recreate the same AI agent, behavior, quality bar, and operational shape every time.  
**Reference product (final outcomes only):** the installed assistant known as Telegram Receipt Analysis Assistant under `/opt/Telegram-Receipt-Analysis-Assistant`  
**Authority order:** This document defines *what* to build and *in what order*. A finished system is correct only when every Acceptance Gate below passes.  
**Language rule for implementers:** Describe and implement the behaviors here. Do not invent alternate architectures (no Google Sheets, no multi-agent mesh, no primary web UI) unless this document is explicitly revised.

---

<!--
=============================================================================
PRIVATE OPERATOR INPUTS + PRE-STEPS (READ BEFORE ANY BUILD OR RUN)
=============================================================================
This workflow deliberately contains NO secrets and NO private account values.
A human operator (or a secure secrets store) MUST supply the private items
below before the finished agent can be configured, started, or acceptance-
tested. Coding agents must NEVER invent, hardcode, commit, or log these
values. Paste them only into a local environment/secrets file that is
gitignored, or into a password manager / OS keyring.

If any REQUIRED item is missing: you may still implement code offline and
run unit tests that mock network — but you must NOT claim the bot is live,
must NOT start long-polling Telegram, and must NOT run end-to-end acceptance.
=============================================================================
-->

# Private information required (operator-supplied)

This logic document is reusable. **Your private credentials and addresses are not inside it.**  
The first successful live build of this product required the operator to provide personal/account data of the kinds listed below. Collect them **before** building for production run, and **before** any live Telegram / xAI / SMTP traffic.

## Why these are required

| Private input | Why the agent cannot run without it |
|---------------|-------------------------------------|
| Telegram Bot Token (from BotFather) | The bot identity on Telegram; every receive/send call authenticates with it |
| xAI / Grok access (API key **and/or** Hermes-compatible xAI OAuth tokens) | Vision extraction and Q&A chat call xAI; no key/OAuth means no receipt understanding |
| CFO email address | Destination for high-value expense alerts |
| SMTP mailbox + App Password | Sending CFO alerts (consumer Gmail or Outlook-style App Password — not the normal login password) |
| Optional Telegram user allowlist IDs | If you lock the bot to specific people, those numeric Telegram user IDs are personal |
| Host / path choices | Where the process runs and where the Excel ledger file lives (may include personal home or OneDrive paths) |

**Never commit** tokens, OAuth refresh tokens, App Passwords, or full `.env` contents to git, tickets, or chat logs. If a Telegram token was ever pasted into a chat, **rotate it in BotFather** and update secrets.

## Checklist of private items to gather

### Required for a live bot (message → extract → Excel)

| # | Item | Where you get it | Example shape only (not real values) |
|---|------|------------------|--------------------------------------|
| 1 | **Telegram Bot Token** | Telegram [@BotFather](https://t.me/BotFather) → create bot or show token | `digits:alphanumeric_string` |
| 2 | **Telegram bot username** (for humans to find the bot) | BotFather when the bot is created | `@YourExpenseBot` |
| 3 | **xAI Grok access** — pick at least one path | | |
| 3a | *Path A:* **xAI API key** | xAI console / account API keys | long secret string |
| 3b | *Path B:* **Hermes xAI OAuth** already logged in on the build host | Run Hermes model/login for xAI Grok OAuth (SuperGrok / entitled account); tokens land in Hermes auth store | OAuth access + refresh tokens managed by Hermes — do not paste into git |
| 4 | **Model id** (if not using default) | xAI model list; product default is Grok 4.1 Fast class | e.g. grok-4-1-fast |

### Required for CFO email alerts (Total above threshold)

| # | Item | Where you get it | Notes |
|---|------|------------------|-------|
| 5 | **CFO destination email** | Business / personal inbox that should receive alerts | Full address |
| 6 | **SMTP username (sender mailbox)** | The mailbox that will send mail | Full address, e.g. operator Gmail |
| 7 | **SMTP App Password** | Provider security settings after **2-Step Verification** is on | Gmail: Google Account → App Passwords; not your normal password |
| 8 | **SMTP From address** | Usually same as sender mailbox | Must be allowed to send as that address |
| 9 | **SMTP host / port** | Provider docs | Gmail typical: host `smtp.gmail.com`, port `587`, STARTTLS |

### Optional but commonly private

| # | Item | When needed |
|---|------|-------------|
| 10 | **Allowed Telegram user IDs** | Restrict who may use the bot (numeric IDs from Telegram) |
| 11 | **Expense threshold override** | If not using default 500 |
| 12 | **Excel file path / sheet name** | If not using defaults under project `data/` |
| 13 | **Always-on host identity** | Which machine runs long polling (lab server, workstation, etc.) |
| 14 | **Hermes home path** | If OAuth path is used and Hermes is not in the default location |

<!--
OPERATOR FILL-IN TEMPLATE (copy to a private notes file or password manager — NOT into git)

Telegram bot token:        <PASTE ONLY IN SECRETS STORE>
Telegram bot username:     <e.g. @...>
xAI API key (if used):     <PASTE ONLY IN SECRETS STORE>
Hermes xAI OAuth:          <confirm logged-in on host: yes/no>
CFO email:                 <name@domain>
SMTP user / from:          <name@domain>
SMTP app password:         <PASTE ONLY IN SECRETS STORE>
SMTP host:port:            <e.g. smtp.gmail.com / 587>
Allowed Telegram user IDs: <comma-separated or empty for open>
Expense threshold:         <default 500>
Workbook path:             <default project data/expenses.xlsx>
Run host:                  <hostname>

DO NOT put real values back into LOGIC_WORKFLOW.md.
-->

---

# Pre-steps before building or running this logic document

Complete these in order. **Do not start live run (Part E7+ / E10) until Required Live block is done.**

## Pre-step 0 — Decide scope of this run

| Mode | You may do | You must not do |
|------|------------|-----------------|
| **Offline build** | Implement layers, unit tests with mocks, package layout | Call real Telegram, xAI, or SMTP with missing secrets |
| **Live configure** | Write secrets into local env/secret store only | Commit secrets; paste secrets into this document |
| **Live run + E2E** | Long poll, real photos, real CFO email tests | Claim success if any Required Live item is missing |

## Pre-step 1 — Accounts and entitlements

1. **Telegram:** Account able to talk to BotFather; create or select the bot that will be this agent. Save the **bot token** and **bot username** privately.  
2. **xAI / Grok:** Account entitled to API and/or Grok OAuth as you intend to use. Confirm vision-capable model access (Grok 4.1 Fast class).  
3. **If using Hermes OAuth:** On the **same host** that will run the bot, complete Hermes xAI Grok OAuth login so the auth store has usable access + refresh tokens. Confirm refresh works (Hermes can call xAI).  
4. **Mail:** Choose sender mailbox (Gmail App Password path recommended). Enable **2-Step Verification**, then create a **Mail App Password**.  
5. **CFO inbox:** Confirm the real destination address that should receive alerts (may be personal or business).  
6. **Optional allowlist:** List numeric Telegram user IDs allowed to use the bot.

## Pre-step 2 — Host and network

1. Choose an **always-on** (or at-least-while-in-use) machine for long polling.  
2. Ensure outbound network access to:  
   - Telegram Bot API host  
   - xAI API host (and xAI auth host if OAuth refresh is used)  
   - SMTP host on the submission port (e.g. 587)  
3. Ensure a **writable data directory** for the Excel ledger and SQLite state.  
4. If OAuth write-through to Hermes auth store is used, that auth directory must be **readable and writable** by the bot process user.

## Pre-step 3 — Secret material staging (no git)

1. Create a **local secrets/env file** outside source control (or gitignored).  
2. Place into it only: Telegram token, xAI key (if any), SMTP password, CFO email, SMTP user/from, paths, threshold, allowlist.  
3. Verify ignore rules so `data/`, env files, and secret dumps cannot be committed.  
4. If any secret was exposed in chat or tickets: **rotate** it before go-live.

## Pre-step 4 — Gmail App Password quick path (when using Gmail SMTP)

1. Turn on 2-Step Verification for the sender Google account.  
2. Open Google App Passwords; create one for Mail.  
3. Store the 16-character password as the SMTP password secret (spaces optional; strip at use).  
4. SMTP host `smtp.gmail.com`, port `587`, STARTTLS.  
5. Do not use the normal Google account password for SMTP.

## Pre-step 5 — Pre-build readiness gate (must all be true for live E2E)

| # | Check | Offline build OK if false? | Live E2E OK if false? |
|---|--------|----------------------------|------------------------|
| 1 | Telegram bot token in secrets store | Yes | **No** |
| 2 | xAI API key **or** working Hermes xAI OAuth on host | Yes (mock tests) | **No** |
| 3 | CFO email decided | Yes | **No** (alert scenarios) |
| 4 | SMTP user + App Password + host/port in secrets | Yes | **No** (alert scenarios) |
| 5 | Data directory writable on run host | Yes | **No** |
| 6 | Outbound HTTPS/SMTP from run host works | Yes | **No** |
| 7 | Operator understands tokens must not be committed | **No** — stop | **No** — stop |

**Rule:** You may execute Part E0–E6 style implementation and offline tests with mocks while secrets are incomplete. You may **not** mark Part E10 complete without the Live E2E column all “Yes.”

## Pre-step 6 — After secrets exist, before first live message

1. Load configuration from the secrets/env store only.  
2. Start process; confirm Telegram identity check succeeds (bot token valid).  
3. Confirm Grok credential resolves (static key or OAuth refresh path).  
4. Send a low-value test receipt before testing CFO threshold mail.  
5. For CFO path: use a test total above threshold and confirm inbox + Excel CFO timestamp column.  
6. Back up the Excel file after first successful rows.

<!--
BUILD AGENT INSTRUCTIONS (comments for implementers / Hermes):
- Treat "Private information required" and "Pre-steps" as blocking for live run.
- Never ask the user to paste secrets into this markdown file.
- Never echo secrets back in full in logs or final reports (presence/length only).
- If secrets missing: implement + unit test only; list which pre-steps remain.
- Reference product path is for behavioral comparison only, not a license to
  dump production .env into the workflow doc.
-->

---

# Part A — Product Identity

## A1. Problem statement

Employees submit receipt or invoice images through Telegram. Manual entry is slow and inconsistent. The business needs:

1. Automatic extraction of expense fields from images  
2. Durable logging into a local spreadsheet  
3. Automatic CFO alert when a transaction exceeds a money threshold  
4. Natural-language questions answered from logged data  
5. Continuous conversation in the same Telegram chat  

## A2. Solution identity (fixed)

| Dimension | Fixed choice |
|-----------|----------------|
| Agent type | Single agent, single long-running process |
| Channel | Telegram bot (long polling) |
| Vision + chat model | Grok 4.1 Fast class model (vision for images; chat for Q&A) |
| Primary datastore | One local Excel workbook (`.xlsx`) only |
| Auxiliary state | SQLite for session continuity and message idempotency |
| CFO notification | Consumer mailbox SMTP with App Password (Gmail preferred path) |
| Google Workspace / Sheets / Gmail API | Out of scope — not used |
| Multi-agent orchestration | Out of scope |
| Web UI as primary interface | Out of scope |

## A3. Actors

| Actor | Role |
|-------|------|
| Employee | Sends photos/text on Telegram |
| Bot agent | Extracts, logs, answers, alerts |
| CFO | Receives high-value email alerts only |
| Operator | Configures secrets, host, backups |

## A4. Trigger

Every new Telegram message to the bot is a trigger. Frequency is ad-hoc per receipt or question.

---

# Part B — Canonical Schemas

These schemas are immutable for a “same product” rebuild. Rename or reorder only with a versioned migration plan and full regression.

## B1. Configuration schema (secrets and settings)

All secrets live in an environment file never committed to source control. Names below are the logical keys.

| Key | Required | Meaning | Default / notes |
|-----|----------|---------|-----------------|
| Telegram bot token | Yes | BotFather token | — |
| xAI credential | Yes* | API access for Grok | Static API key and/or Hermes-compatible OAuth access that can refresh |
| xAI model id | No | Model name for vision and chat | Grok 4.1 Fast class id |
| xAI base URL | No | Inference host | Official xAI HTTPS API host only |
| Expense workbook path | No | Path to `.xlsx` | Project `data/expenses.xlsx` |
| Expense sheet name | No | Tab inside workbook | `Expenses` |
| Expense threshold | No | CFO alert if Total greater than this | `500` |
| CFO email | Yes for alerts | Destination mailbox | — |
| SMTP host | Yes for alerts | Mail server | Gmail SMTP host |
| SMTP port | Yes for alerts | Submission port | `587` with STARTTLS |
| SMTP user | Yes for alerts | Full mailbox address used to authenticate | e.g. operator Gmail |
| SMTP password | Yes for alerts | App Password (not normal login password) | 16-char app password style |
| SMTP from | No | From header | Usually same as SMTP user |
| Allowed Telegram user ids | No | Comma-separated allowlist | Empty means allow all |
| Database path | No | SQLite file | Project `data/bot.db` |
| Log level | No | Process logging verbosity | `INFO` |
| Optional env file path override | No | Absolute path to env file for services | For systemd/service hosts |

\*Credential policy: prefer a durable refreshable OAuth path compatible with Hermes xAI OAuth when available; static API key is acceptable fallback. Never log tokens or passwords.

## B2. Expense category schema (closed set)

Exactly four values. No others.

| Category value |
|----------------|
| Travel |
| Food |
| Equipment |
| Other |

Normalization rule: free-text synonyms from the model (meal, dining, gear, etc.) must coerce into this set; unknown → Other.

## B3. Vision extraction result schema

The vision step must return a single structured object with these logical fields:

| Field | Type | Rules |
|-------|------|--------|
| is_receipt | boolean | False if image is not a receipt/invoice |
| vendor | text | Merchant name; empty if unknown |
| expense_date | date or null | Prefer ISO calendar date `YYYY-MM-DD` |
| currency | text | Default `USD` if unknown |
| total | number or null | Grand total paid; plain number, no currency symbols |
| tax | number or null | Tax only; use 0 if unknown after acceptance |
| category | enum | One of B2 |
| notes | text | Brief line-item / items summary |
| confidence | number 0–1 | Model confidence |
| error | text | Optional machine error detail (not always shown raw to user) |

## B4. Excel row schema (authoritative column order)

Workbook sheet starts with a header row. Every logged expense is one data row. Column order and names are fixed:

| Order | Column name | Type / encoding | Source |
|------:|-------------|-----------------|--------|
| 1 | TelegramUserId | integer | Telegram user |
| 2 | TelegramUsername | text | Username or display name |
| 3 | ReceiptFileId | text | Telegram file id |
| 4 | Vendor | text | Extraction |
| 5 | ExpenseDate | text `YYYY-MM-DD` | Extraction (default today if missing after acceptance) |
| 6 | Currency | text | Extraction |
| 7 | Total | number | Extraction or user-supplied completion |
| 8 | Tax | number | Extraction (0 if unknown) |
| 9 | Category | text enum B2 | Extraction |
| 10 | Notes | text | Extraction items summary |
| 11 | Confidence | number 0–1 | Extraction |
| 12 | NeedsReview | boolean as `TRUE`/`FALSE` text | Policy (low confidence or incomplete) |
| 13 | MessageId | integer | Telegram message id (idempotency aid) |
| 14 | Over500 | boolean as `TRUE`/`FALSE` text | Derived: Total > threshold |
| 15 | CFOEmailSentAt | text ISO UTC or empty | Set only after successful SMTP send |

Derived fields must not be trusted from the model; compute Over500 from Total and threshold.

## B5. SQLite logical stores

| Store | Purpose | Key ideas |
|-------|---------|-----------|
| Processed messages | Idempotency | Unique pair (chat id, message id) |
| Sessions | Optional light continuity | Keyed by chat id |
| Pending | Incomplete receipts | Keyed by chat id; holds partial extraction until user supplies missing total |

## B6. CFO email schema

| Element | Content |
|---------|---------|
| Condition | Total strictly greater than configured threshold |
| To | CFO email |
| From | SMTP from / user |
| Subject pattern | Expense alert including currency, total, vendor, category |
| Body fields | Vendor, date, total, tax, category, notes, Telegram user id/username, message id, needs review, confidence, alert timestamp UTC |
| On success | Write CFOEmailSentAt on the Excel row |
| On failure | Keep Excel row; do not crash process; user may be told email failed |

## B7. Q&A tool capability schema

When the user asks spend questions, the agent may use only these logical tools over Excel (never invent totals):

| Tool | Purpose | Typical filters |
|------|---------|-----------------|
| Sum expenses | Numeric total of Total column | category, date from/to, telegram user id |
| Query expenses | List matching rows (capped) | same filters |
| List recent | Last N expenses for a user | n, telegram user id |

Default scope: requesting user’s own Telegram user id unless an explicit admin policy says otherwise.

## B8. Fixed user-facing messages (stable UX)

| Situation | Required user-visible meaning (wording must stay recognizable) |
|-----------|------------------------------------------------------------------|
| Unauthorized user | Unauthorized |
| Duplicate message | Already logged this message |
| Not a receipt | This doesn't appear to be a receipt or invoice. Please send a relevant image. |
| Unclear / unreadable | Could not extract data. Please send a clearer image. |
| Missing total | Ask user to reply with the numeric total; hold pending state |
| Temporary Excel/IO failure | Temporary issue; try again later |
| Model/API failure | Temporary model/backend error; do not fabricate a receipt |
| Success log | Confirm vendor, total, category, and that the row was saved; mention CFO email if sent or if email failed |

Do not casually “improve” these phrases; consistency is part of product quality.

---

# Part C — Runtime Logic (Decision Workflow)

## C1. Top-level message router

```
ON telegram_message:
  IF allowlist configured AND user not in allowlist:
      REPLY unauthorized
      STOP

  IF message is image (photo OR image document):
      RUN Image Expense Workflow (C2)
  ELSE IF message is plain text:
      RUN Text Workflow (C3)
  ELSE:
      REPLY ask for receipt photo or text question
```

## C2. Image expense workflow

```
INPUT: image bytes, mime, telegram user, chat id, message id, file id

1. IDEMPOTENCY
   IF (chat id, message id) already processed:
      REPLY already logged
      STOP

2. EXTRACT
   Call Grok vision with extraction schema B3
   IF transport/model error:
      REPLY temporary model error
      STOP

3. CLASSIFY OUTCOME
   IF is_receipt is false:
      MARK processed (optional: still mark to avoid loops — prefer mark)
      REPLY non-receipt fixed copy
      STOP

   IF confidence very low AND total is null:
      REPLY unclear image fixed copy
      STOP  (do not append incomplete garbage)

   IF total is null (but otherwise looks like a receipt):
      SAVE pending state for this chat (extraction + file id + message metadata)
      REPLY ask user for total amount
      STOP

4. BUILD ROW
   Map extraction + telegram metadata → Excel row schema B4
   Compute Over500 from Total and threshold
   Set NeedsReview if confidence below review policy threshold
   Set CFOEmailSentAt empty

5. PERSIST
   Append row to Excel under file lock
   MARK (chat id, message id) processed
   IF Excel fails:
      REPLY temporary sheet issue
      STOP (do not mark processed if nothing written — or mark only after durable write; durable write first is required)

6. CFO ALERT (best effort)
   IF Total > threshold:
      TRY send SMTP email schema B6
      IF success: update row CFOEmailSentAt
      IF fail: keep row; note email failure in user reply

7. CONFIRM
   REPLY success summary to user
```

## C3. Text workflow

```
INPUT: text, telegram user, chat id, message id

1. PENDING COMPLETION BRANCH
   IF chat has pending missing-total receipt:
      TRY parse a monetary amount from text
      IF parse fails:
         REPLY ask again for a number total
         STOP
      MERGE amount into pending extraction
      CLEAR pending
      CONTINUE from C2 step 4 (BUILD ROW) using pending image metadata
      (Use original receipt message id / file id from pending)

2. Q&A BRANCH
   Interpret user question with Grok chat
   WHEN numbers about spending are needed:
      MUST call Excel tools (B7)
      MUST answer only from tool results
      MUST NOT invent totals or rows
   REPLY concise answer
```

## C4. Session continuity rules

| Rule | Logic |
|------|--------|
| Session key | Telegram chat id |
| Continuous chat | Same chat retains pending state and conversational Q&A context as designed |
| Idempotency key | Pair (chat id, message id) |
| Double submit | Second delivery of same message id must not create a second Excel row |
| Pending lifetime | Until completed with a total or explicitly abandoned by policy (default: until completed) |

## C5. Credential resolution order for Grok (quality + ops)

```
IF Hermes-compatible xAI OAuth is enabled AND auth store has tokens:
   Read access token from Hermes auth store
   IF token near expiry (proactive skew, up to about one hour early for long-lived tokens;
      tighter skew for short-lived tokens):
      Acquire auth store lock
      Refresh with OAuth refresh_token grant against official xAI auth token endpoint
      Persist rotated access token AND refresh token back to the same auth store
         (refresh tokens rotate — failing to write back breaks all consumers)
   Use access token as bearer for inference
   IF inference returns unauthorized:
      Force one refresh and retry once
ELSE:
   Use static xAI API key from configuration
```

Never send bearer tokens to non-xAI hosts.

---

# Part D — Logical Architecture (layers, not files-as-code)

Build as separated responsibilities. Thin channel adapters; fat orchestration; pure stores.

| Layer | Responsibility | Must not do |
|-------|----------------|-------------|
| Channel adapter (Telegram) | Receive updates, enforce allowlist, download media, send replies, typing indicators | Business decisions, spreadsheet math, SMTP policy |
| Orchestration service | Own C2/C3 branches end-to-end | Direct Telegram protocol details beyond a small user context object |
| Vision/chat gateway | Call Grok; parse structured extraction; expose Q&A tools | Write Excel; send email |
| Workbook store | Create workbook/headers if missing; append; query; sum; update CFO timestamp; file locking | Talk to Telegram or Grok |
| Mail gateway | Send CFO alert only when asked | Decide threshold |
| State database | Processed keys, pending payloads, light session | Become the expense ledger of record |
| Configuration loader | Read env schema B1 | Hardcode secrets |

**Process model:** one bot process preferred so Excel locking stays simple.

**Deploy shape (reference outcome):** always-on host service, working directory with `data/` writable, outbound HTTPS to Telegram API, xAI API, and SMTP submission port.

---

# Part E — Build Workflow (repeatable task order)

Execute tasks **in order**. Do not skip upstream schemas. Each task ends only when its gate passes.

## E0. Preconditions and secrets hygiene

**Do:**
- Create greenfield project identity for this assistant  
- Establish ignore rules so secrets and `data/` artifacts are never committed  
- Obtain Telegram bot token (rotate if it was ever pasted into chat logs)  
- Obtain xAI access (API key and/or Hermes OAuth already working)  
- Decide SMTP sender mailbox; enable 2-Step Verification; create App Password  
- Decide CFO destination address  
- Decide host machine for long polling  

**Gate E0:** Secrets exist only in env/secret store; no Google Workspace requirement remains in the design.

## E1. Domain schema

**Do:**
- Implement category closed set B2  
- Implement expense row mapping to B4 including derived Over500  
- Implement extraction object B3  
- Unit-test: threshold boundary (equal to threshold is NOT over; greater is over)  
- Unit-test: category coercion  

**Gate E1:** Schema tests pass without network.

## E2. Vision extraction gateway

**Do:**
- Define system instructions that force single JSON object matching B3  
- Categories constrained to B2  
- Non-receipt and low-confidence behaviors supported  
- Unit-test parsing of model output (including fenced JSON tolerance if allowed) with mocks — no live key required  

**Gate E2:** Parser/contract tests pass offline.

## E3. Excel workbook store (ledger of record)

**Do:**
- Ensure workbook + header row B4 if missing  
- Append expense rows under exclusive file lock  
- Query/filter/sum/list recent  
- Update CFO sent timestamp by message id  
- Booleans stored consistently as TRUE/FALSE text  
- Unit-test on temporary workbook paths  

**Gate E3:** Append → query → sum proven in automated tests; lock strategy documented in runbook.

## E4. SMTP CFO alert gateway

**Do:**
- STARTTLS submit using B1 SMTP fields  
- Subject/body per B6  
- Strip spaces from app passwords if providers display grouped characters  
- Unit-test with mocked SMTP  

**Gate E4:** Success returns a timestamp string; failure raises/returns error without crashing the host process when orchestration catches it.

## E5. SQLite state

**Do:**
- Processed message uniqueness  
- Pending payload per chat  
- Session record if needed for continuity  

**Gate E5:** Duplicate processed check and pending set/get/clear tested.

## E6. Orchestration service

**Do:**
- Encode full C2 and C3 logic  
- On email failure after successful Excel write: still confirm log; mention email failure  
- On Excel failure: do not claim success  
- Wire vision, workbook, mail, state  

**Gate E6:** Branch tests or scenario tests cover: non-receipt, unclear, missing total → completion text, over-threshold email attempt, Q&A uses tools.

## E7. Telegram channel adapter

**Do:**
- Commands: start and help explaining photo log + Q&A + CFO threshold behavior  
- Handlers: photo, image document, text  
- Optional allowlist  
- Pass a minimal user context (chat id, user id, username, message id) into orchestration  

**Gate E7:** Manual or automated smoke: process starts with token and reaches Telegram getMe success.

## E8. Q&A over Excel

**Do:**
- Expose tools B7 to chat model  
- Default filter to requesting user  
- Prompt rule: never invent numbers  

**Gate E8:** With known seed rows, a Food/month question returns the seeded sum.

## E9. Packaging, docs, operations

**Do:**
- Installable package layout with virtual environment  
- Setup / run / test entry scripts for Linux and optionally Windows  
- README + runbook: env keys, Gmail App Password steps, backup of workbook, token rotation  
- Service unit on always-on host: restart on failure; writable data dir; if using Hermes OAuth write-through, auth store directory must be writable  

**Gate E9:** Fresh machine can setup → test → run using docs only.

## E10. End-to-end acceptance (product sameness)

All boxes required:

| # | Scenario | Pass criteria |
|---|----------|----------------|
| 1 | Clear receipt photo | One new Excel row; user confirmation; columns B4 populated sensibly |
| 2 | Text spend question | Answer matches Excel tool math; no hallucinated total |
| 3 | Total greater than threshold | CFO email received; Over500 true; CFOEmailSentAt set |
| 4 | Total equal to threshold | No CFO email; Over500 false |
| 5 | Blurry receipt | Unclear fixed copy; no junk row (or needs-review policy honored) |
| 6 | Non-receipt image | Non-receipt fixed copy |
| 7 | Missing total then user replies “123.45” | Single completed row with that total |
| 8 | Duplicate delivery same message id | Still one row only |
| 9 | SMTP down after good row | Row remains; process stays up; user informed of email issue |
| 10 | Repo/secrets hygiene | No Google Sheets client; no committed secrets; data dir gitignored |
| 11 | Model identity | Requests use configured Grok 4.1 Fast class model |
| 12 | Same-chat follow-up | Pending and Q&A continuity work in one chat id |

**Gate E10:** All twelve pass on the target host. Only then is the build “the same product.”

---

# Part F — Quality System (consistent code quality without pasting code)

## F1. Design laws

1. **One ledger:** Excel is the expense system of record. SQLite is not a second ledger.  
2. **One orchestrator:** All business branching lives in one service layer.  
3. **Thin edges:** Telegram handlers only adapt I/O.  
4. **Closed categories:** Never expand B2 silently.  
5. **Closed columns:** Never reorder B4 silently.  
6. **Idempotent intake:** Same Telegram message never double-logs.  
7. **Best-effort alert:** Email failure must not erase a successful log.  
8. **Tool-grounded answers:** Spend numbers come from Excel tools only.  
9. **Secrets isolation:** Env/secret store only; never source control; never logs.  
10. **No Google dependency** for core path.  
11. **Deterministic edge copy:** Fixed phrases in B8.  
12. **Test pyramid:** Schema and stores offline-tested before live Telegram.

## F2. Implementation order law

Schemas → vision contract → Excel store → mail → state DB → orchestration → Telegram → Q&A → docs/ops → E2E.  
Reversing this order is a quality defect even if demos “work once.”

## F3. Change control law

For any later change:

1. Map the change to exactly one layer in Part D  
2. If B2/B3/B4/B8 change, update this document in the same change set  
3. Add or update automated tests for pure logic  
4. Re-run offline test suite  
5. Re-run affected E10 scenarios  
6. Report: what behavior changed, which gates re-passed  

## F4. Non-goals (reject as scope creep)

- Google Sheets or Drive as primary store  
- Gmail API / Workspace-only mail  
- Multi-agent handoffs for the happy path  
- Payments, OCR vendors other than Grok (unless this document is revised)  
- Automatic multi-currency threshold intelligence  
- Bulk mailing  
- Destructive “fix by deleting the workbook” as a normal troubleshooting step  

## F5. Risks and standard mitigations

| Risk | Mitigation |
|------|------------|
| Excel corruption from concurrent writers | Single bot process + exclusive file lock |
| Cloud sync locks on workbook path | Prefer local `data/` path; copy out for sharing |
| Consumer SMTP daily caps | Alerts only; not bulk mail |
| OAuth refresh token rotation | Always persist new refresh token under lock |
| Token pasted in chat | Rotate Telegram token in BotFather |
| Model hallucination on Q&A | Mandatory tools; prompt forbids invention |
| Partial extraction | Pending total flow; NeedsReview flag |

## F6. Operator checklist (steady state)

| Cadence | Action |
|---------|--------|
| Continuous | Process supervisor restart on failure |
| Weekly | Backup expenses workbook |
| On auth errors | Re-validate xAI credential / Hermes OAuth login |
| On mail errors | Re-validate App Password and 2FA |
| On bot silence | Check host network to Telegram and process status |

---

# Part G — Minimal Operator Story (reference deployment outcome)

A correct deployment looks like this operationally (paths may vary by host; behaviors must not):

1. Bot process runs continuously under a service user  
2. Workbook and SQLite live in a writable data directory  
3. Environment supplies B1 keys  
4. Employee messages the Telegram bot  
5. Photos become rows; high totals email CFO; questions read the workbook  
6. Operators back up the workbook and never commit secrets  

The reference installation that already embodies these outcomes is the Telegram Receipt Analysis Assistant at `/opt/Telegram-Receipt-Analysis-Assistant`. Use it to **verify sameness of behavior**, not as a requirement to copy source text into this workflow.

---

# Part H — One-Page Build Spine (print this)

1. Freeze schemas B1–B8  
2. Build domain objects and offline tests  
3. Build vision contract + offline parse tests  
4. Build locked Excel ledger + tests  
5. Build SMTP alert + tests  
6. Build SQLite idempotency/pending + tests  
7. Build orchestration for image and text trees C2–C3  
8. Build Telegram adapter (start/help/photo/document/text)  
9. Build Q&A tools grounded on Excel  
10. Package, document App Password + backup + service  
11. Pass all E10 acceptance rows  
12. Only then declare feature-complete parity with the reference product  

---

**Document version:** 1.0  
**Sources synthesized:** original agent brief; Hermes implementation plan (Excel-only v2); reference product behavior at `/opt/Telegram-Receipt-Analysis-Assistant`  
**Contains no source code by design** so any competent implementer or coding agent can regenerate equivalent quality systems from logic and schema alone.
