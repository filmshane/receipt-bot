from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Optional

from receipt_bot.config import Settings
from receipt_bot.db import Database
from receipt_bot.llm.grok_client import EXPENSE_TOOLS, GrokClient
from receipt_bot.models import Category, ExpenseRow, ExtractionResult
from receipt_bot.notify.smtp_alert import send_cfo_alert
from receipt_bot.sheets.excel_store import ExcelExpenseStore

log = logging.getLogger(__name__)


@dataclass
class UserContext:
    chat_id: int
    user_id: int
    username: str
    message_id: int


class ExpenseService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = ExcelExpenseStore(
            settings.resolve_xlsx(), settings.expense_sheet_name
        )
        self.db = Database(settings.resolve_db())
        self.grok = GrokClient(
            settings.xai_api_key,
            settings.xai_model,
            settings.xai_base_url,
            use_hermes_oauth=settings.xai_use_hermes_oauth,
            hermes_home=(settings.hermes_home or None) or None,
            token_file=(settings.xai_token_file or None) or None,
        )
        self.store.ensure_workbook()

    async def handle_image(
        self,
        ctx: UserContext,
        image_bytes: bytes,
        file_id: str,
        mime: str = "image/jpeg",
    ) -> str:
        if self.db.is_processed(ctx.chat_id, ctx.message_id):
            return "Already logged this message."

        extraction = await self.grok.extract_receipt_from_image(image_bytes, mime=mime)
        if extraction.error and not extraction.is_receipt:
            if "not configured" in extraction.error.lower():
                return f"Vision backend error: {extraction.error}"
        if extraction.error and extraction.confidence == 0 and not extraction.vendor:
            if "API" in extraction.error or "Parse" in extraction.error:
                return (
                    "Could not extract data (model error). Please try again later "
                    f"or send a clearer image.\n({extraction.error[:120]})"
                )

        if not extraction.is_receipt:
            self.db.mark_processed(ctx.chat_id, ctx.message_id)
            return "This doesn't appear to be a receipt or invoice. Please send a relevant image."

        if extraction.confidence < 0.35 and extraction.total is None:
            return "Could not extract data. Please send a clearer image."

        if extraction.total is None:
            self.db.set_pending(
                ctx.chat_id,
                {
                    "file_id": file_id,
                    "extraction": extraction.model_dump(mode="json"),
                    "message_id": ctx.message_id,
                    "user_id": ctx.user_id,
                    "username": ctx.username,
                },
            )
            return (
                "I found a receipt but could not read the **total**. "
                "Reply with the total amount (e.g. `42.50`) and optionally "
                "`tax=3.20 category=Food vendor=Starbucks`."
            )

        row = self._row_from_extraction(ctx, extraction, file_id)
        return await self._persist_and_maybe_alert(ctx, row)

    async def handle_text(self, ctx: UserContext, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return "Send a receipt photo or ask about your expenses."

        pending = self.db.get_pending(ctx.chat_id)
        if pending:
            return await self._complete_pending(ctx, pending, text)

        # Quick local intents without LLM when possible
        quick = self._quick_intent(ctx, text)
        if quick is not None:
            self.db.append_session_turn(ctx.chat_id, "user", text)
            self.db.append_session_turn(ctx.chat_id, "assistant", quick)
            return quick

        return await self._chat_qa(ctx, text)

    def _quick_intent(self, ctx: UserContext, text: str) -> Optional[str]:
        t = text.lower().strip()
        if t in ("help", "/help"):
            return (
                "Send a **photo** of a receipt to log it.\n"
                "Ask things like: *How much did I spend on Food last month?*\n"
                "Expenses over "
                f"${self.settings.expense_threshold:.0f} email the CFO."
            )
        # "how much ... food ... last month"
        m = re.search(
            r"(?:how much|total|spent|spend).*?(travel|food|equipment|other)?.*?"
            r"(last\s+month|this\s+month|today)?",
            t,
        )
        if m and ("how much" in t or "total" in t or "spend" in t or "spent" in t):
            cat = m.group(1)
            when = m.group(2) or ""
            category = cat.title() if cat else None
            date_from = date_to = None
            today = date.today()
            if "last month" in when or "last month" in t:
                first_this = today.replace(day=1)
                last_prev = first_this - timedelta(days=1)
                date_from = last_prev.replace(day=1).isoformat()
                date_to = last_prev.isoformat()
            elif "this month" in t:
                date_from = today.replace(day=1).isoformat()
                date_to = today.isoformat()
            total = self.store.sum_total(
                category=category, user_id=ctx.user_id, date_from=date_from, date_to=date_to
            )
            label = category or "all categories"
            period = when or "all time"
            return f"Total for {label} ({period}): **${total:.2f}** (your expenses)."
        return None

    async def _complete_pending(self, ctx: UserContext, pending: dict, text: str) -> str:
        ext = ExtractionResult.model_validate(pending.get("extraction") or {})
        # parse total as first number
        nums = re.findall(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
        if not nums and ext.total is None:
            return "Please send the total as a number, e.g. `42.50`."
        if nums and ext.total is None:
            ext.total = float(nums[0])
        # optional key=value
        for key, val in re.findall(r"(\w+)\s*=\s*([^\s]+)", text):
            k = key.lower()
            if k == "tax":
                ext.tax = float(val.replace("$", ""))
            elif k == "category":
                ext.category = Category.coerce(val)
            elif k == "vendor":
                ext.vendor = val
            elif k == "total":
                ext.total = float(val.replace("$", ""))
        file_id = pending.get("file_id") or ""
        message_id = int(pending.get("message_id") or ctx.message_id)
        row = ExpenseRow(
            telegram_user_id=ctx.user_id,
            telegram_username=ctx.username,
            receipt_file_id=file_id,
            vendor=ext.vendor or "Unknown",
            expense_date=ext.expense_date or date.today().isoformat(),
            currency=ext.currency or "USD",
            total=float(ext.total or 0),
            tax=float(ext.tax or 0),
            category=ext.category,
            notes=ext.notes or text,
            confidence=max(float(ext.confidence or 0), 0.5),
            needs_review=True,
            message_id=message_id,
            threshold=self.settings.expense_threshold,
        )
        self.db.clear_pending(ctx.chat_id)
        # use original message id for idempotency
        ctx_orig = UserContext(
            chat_id=ctx.chat_id,
            user_id=ctx.user_id,
            username=ctx.username,
            message_id=message_id,
        )
        return await self._persist_and_maybe_alert(ctx_orig, row)

    def _row_from_extraction(
        self, ctx: UserContext, ext: ExtractionResult, file_id: str
    ) -> ExpenseRow:
        needs = float(ext.confidence or 0) < 0.6
        return ExpenseRow(
            telegram_user_id=ctx.user_id,
            telegram_username=ctx.username,
            receipt_file_id=file_id,
            vendor=ext.vendor or "Unknown",
            expense_date=ext.expense_date or date.today().isoformat(),
            currency=ext.currency or "USD",
            total=float(ext.total or 0),
            tax=float(ext.tax or 0),
            category=ext.category,
            notes=ext.notes or "",
            confidence=float(ext.confidence or 0),
            needs_review=needs,
            message_id=ctx.message_id,
            threshold=self.settings.expense_threshold,
        )

    async def _persist_and_maybe_alert(self, ctx: UserContext, row: ExpenseRow) -> str:
        try:
            if self.store.find_by_message_id(row.message_id):
                self.db.mark_processed(ctx.chat_id, row.message_id)
                return "Already logged this message."
            self.store.append_expense(row)
        except Exception as e:
            log.exception("excel write failed")
            return f"Temporary issue saving expense to Excel; try again later. ({e})"

        self.db.mark_processed(ctx.chat_id, row.message_id)
        email_note = ""
        if row.over_500:
            try:
                sent_at = await send_cfo_alert(
                    row,
                    threshold=self.settings.expense_threshold,
                    smtp_host=self.settings.smtp_host,
                    smtp_port=self.settings.smtp_port,
                    smtp_user=self.settings.smtp_user,
                    smtp_password=self.settings.smtp_password,
                    smtp_from=self.settings.smtp_from or self.settings.smtp_user,
                    cfo_email=self.settings.cfo_email,
                )
                self.store.update_cfo_sent(row.message_id, sent_at)
                email_note = f"\nCFO alert emailed to {self.settings.cfo_email}."
            except Exception as e:
                log.exception("cfo email failed")
                email_note = f"\nLogged, but CFO email failed: {e}"

        conf = f"{row.confidence:.0%}"
        review = " (flagged for review)" if row.needs_review else ""
        msg = (
            f"Logged expense{review}:\n"
            f"• Vendor: {row.vendor}\n"
            f"• Date: {row.expense_date}\n"
            f"• Total: {row.currency} {row.total:.2f} (tax {row.tax:.2f})\n"
            f"• Category: {row.category.value}\n"
            f"• Confidence: {conf}\n"
            f"Saved to Excel."
            f"{email_note}"
        )
        self.db.append_session_turn(ctx.chat_id, "assistant", msg)
        return msg

    async def _chat_qa(self, ctx: UserContext, text: str) -> str:
        self.db.append_session_turn(ctx.chat_id, "user", text)
        history = self.db.get_turns(ctx.chat_id)
        messages = []
        for turn in history[:-1][-8:]:
            role = turn["role"] if turn["role"] in ("user", "assistant") else "user"
            messages.append({"role": role, "content": turn["content"]})
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{text}\n\n[context: telegram_user_id={ctx.user_id}; "
                    "default filters to this user unless they ask company-wide]"
                ),
            }
        )

        try:
            assistant = await self.grok.chat(messages, tools=EXPENSE_TOOLS)
        except Exception as e:
            log.exception("chat failed")
            return f"Chat backend error: {e}"

        # tool loop (max 3)
        for _ in range(3):
            tool_calls = assistant.get("tool_calls") or []
            if not tool_calls:
                break
            messages.append(assistant)
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._run_tool(ctx, name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "content": json.dumps(result),
                    }
                )
            try:
                assistant = await self.grok.chat(messages, tools=EXPENSE_TOOLS)
            except Exception as e:
                return f"Chat backend error: {e}"

        content = assistant.get("content") or "Done."
        self.db.append_session_turn(ctx.chat_id, "assistant", content)
        return content

    def _run_tool(self, ctx: UserContext, name: str, args: dict) -> Any:
        uid = args.get("telegram_user_id", ctx.user_id)
        category = args.get("category")
        date_from = args.get("date_from")
        date_to = args.get("date_to")
        if name == "sum_expenses":
            return {
                "total": self.store.sum_total(
                    category=category,
                    user_id=uid,
                    date_from=date_from,
                    date_to=date_to,
                )
            }
        if name == "query_expenses":
            rows = self.store.query(
                category=category, user_id=uid, date_from=date_from, date_to=date_to
            )
            return {"count": len(rows), "rows": rows[:50]}
        if name == "list_recent":
            n = int(args.get("n") or 10)
            return {"rows": self.store.list_recent(n=n, user_id=uid)}
        return {"error": f"unknown tool {name}"}
