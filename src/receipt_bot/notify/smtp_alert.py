from __future__ import annotations

from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Optional

import aiosmtplib

from receipt_bot.models import ExpenseRow


async def send_cfo_alert(
    row: ExpenseRow,
    *,
    threshold: float,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_from: str,
    cfo_email: str,
) -> str:
    """Send CFO alert via Gmail SMTP. Returns ISO timestamp UTC on success."""
    if not cfo_email:
        raise ValueError("CFO_EMAIL is not configured")
    if not smtp_user or not smtp_password:
        raise ValueError("SMTP_USER / SMTP_PASSWORD not configured")

    sent_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    msg = EmailMessage()
    msg["From"] = smtp_from or smtp_user
    msg["To"] = cfo_email
    msg["Subject"] = (
        f"[Expense Alert] {row.currency} {row.total:.2f} — {row.vendor or 'Unknown'} "
        f"({row.category.value})"
    )
    msg.set_content(
        f"A transaction exceeded ${threshold:.2f}.\n\n"
        f"Vendor: {row.vendor}\n"
        f"Date: {row.expense_date}\n"
        f"Total: {row.currency} {row.total:.2f}\n"
        f"Tax: {row.currency} {row.tax:.2f}\n"
        f"Category: {row.category.value}\n"
        f"Notes: {row.notes}\n"
        f"Telegram user: @{row.telegram_username} ({row.telegram_user_id})\n"
        f"Message ID: {row.message_id}\n"
        f"Needs review: {row.needs_review}\n"
        f"Confidence: {row.confidence}\n"
        f"Alert time (UTC): {sent_at}\n"
    )

    await aiosmtplib.send(
        msg,
        hostname=smtp_host,
        port=smtp_port,
        username=smtp_user,
        password=smtp_password.replace(" ", ""),  # Gmail app passwords often shown with spaces
        start_tls=True,
    )
    return sent_at
