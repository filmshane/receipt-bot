from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from receipt_bot.bot import handlers
from receipt_bot.config import Settings, get_settings
from receipt_bot.services.expense_service import ExpenseService


def build_app(settings: Settings | None = None) -> Application:
    settings = settings or get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN missing. Copy .env.example to .env and set the token "
            "(rotate if it was ever pasted in chat)."
        )

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )
    app.bot_data["expense_service"] = ExpenseService(settings)
    app.bot_data["allowed_ids"] = settings.allowed_ids()

    app.add_handler(CommandHandler("start", handlers.start_cmd))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handlers.on_photo))
    app.add_handler(
        MessageHandler(filters.Document.IMAGE, handlers.on_document)
    )
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text)
    )
    return app


def main() -> None:
    settings = get_settings()
    app = build_app(settings)
    logging.getLogger(__name__).info(
        "Starting Receipt Analysis Assistant (Excel=%s, SMTP=%s)",
        settings.resolve_xlsx(),
        settings.smtp_host,
    )
    app.run_polling(allowed_updates=["message"])
