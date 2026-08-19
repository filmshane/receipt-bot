from __future__ import annotations

import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from receipt_bot.services.expense_service import ExpenseService, UserContext

log = logging.getLogger(__name__)


def _svc(context: ContextTypes.DEFAULT_TYPE) -> ExpenseService:
    return context.application.bot_data["expense_service"]


def _allowed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    ids = context.application.bot_data.get("allowed_ids")
    if ids is None:
        return True
    return user_id in ids


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if not _allowed(context, update.effective_user.id):
        await update.message.reply_text("Unauthorized.")
        return
    await update.message.reply_text(
        "Telegram Receipt Analysis Assistant\n\n"
        "• Send a receipt/invoice **photo** to log an expense to Excel.\n"
        "• Ask questions e.g. \"How much did I spend on Food last month?\"\n"
        "• Expenses over the threshold email the CFO via Gmail SMTP.\n"
        "Commands: /start /help"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_cmd(update, context)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        return
    user = update.effective_user
    if not _allowed(context, user.id):
        await update.message.reply_text("Unauthorized.")
        return

    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    bio = await tg_file.download_as_bytearray()
    ctx = UserContext(
        chat_id=update.effective_chat.id,
        user_id=user.id,
        username=user.username or user.full_name or "",
        message_id=update.message.message_id,
    )
    await update.message.chat.send_action("typing")
    try:
        reply = await _svc(context).handle_image(
            ctx, bytes(bio), file_id=photo.file_id, mime="image/jpeg"
        )
    except Exception as e:
        log.exception("photo handler")
        reply = f"Error processing image: {e}"
    await update.message.reply_text(reply)


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        return
    user = update.effective_user
    if not _allowed(context, user.id):
        await update.message.reply_text("Unauthorized.")
        return
    doc = update.message.document
    if not doc:
        return
    mime = doc.mime_type or ""
    if not mime.startswith("image/"):
        await update.message.reply_text("Please send an image file (receipt photo).")
        return
    tg_file = await context.bot.get_file(doc.file_id)
    bio = await tg_file.download_as_bytearray()
    ctx = UserContext(
        chat_id=update.effective_chat.id,
        user_id=user.id,
        username=user.username or user.full_name or "",
        message_id=update.message.message_id,
    )
    await update.message.chat.send_action("typing")
    try:
        reply = await _svc(context).handle_image(
            ctx, bytes(bio), file_id=doc.file_id, mime=mime or "image/jpeg"
        )
    except Exception as e:
        log.exception("document handler")
        reply = f"Error processing image: {e}"
    await update.message.reply_text(reply)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        return
    user = update.effective_user
    if not _allowed(context, user.id):
        await update.message.reply_text("Unauthorized.")
        return
    text = update.message.text or ""
    ctx = UserContext(
        chat_id=update.effective_chat.id,
        user_id=user.id,
        username=user.username or user.full_name or "",
        message_id=update.message.message_id,
    )
    await update.message.chat.send_action("typing")
    try:
        reply = await _svc(context).handle_text(ctx, text)
    except Exception as e:
        log.exception("text handler")
        reply = f"Error: {e}"
    await update.message.reply_text(reply)
