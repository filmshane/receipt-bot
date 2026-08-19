from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: .../Telegram-Receipt-Analysis-Assistant
ROOT = Path(__file__).resolve().parents[2]


def _env_file() -> str:
    # Allow override for systemd/docker: RECEIPT_BOT_ENV=/etc/receipt-bot.env
    override = os.environ.get("RECEIPT_BOT_ENV")
    if override:
        return override
    return str(ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    xai_api_key: str = ""
    xai_model: str = "grok-4-1-fast"
    xai_base_url: str = "https://api.x.ai/v1"
    # Use Hermes ~/.hermes/auth.json xAI OAuth + same refresh method as Hermes (default on).
    xai_use_hermes_oauth: bool = True
    hermes_home: str = ""
    # Legacy optional access-token file; OAuth auth.json is preferred.
    xai_token_file: str = ""

    expense_xlsx_path: str = ""
    expense_sheet_name: str = "Expenses"
    expense_threshold: float = 500.0

    cfo_email: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = "shane92584@gmail.com"
    smtp_password: str = ""
    smtp_from: str = "shane92584@gmail.com"

    allowed_telegram_user_ids: str = ""
    database_path: str = ""
    log_level: str = "INFO"

    def allowed_ids(self) -> Optional[List[int]]:
        raw = (self.allowed_telegram_user_ids or "").strip()
        if not raw:
            return None
        out: List[int] = []
        for part in raw.split(","):
            part = part.strip()
            if part:
                out.append(int(part))
        return out or None

    def resolve_xlsx(self) -> Path:
        raw = (self.expense_xlsx_path or "").strip()
        p = Path(raw) if raw else (ROOT / "data" / "expenses.xlsx")
        if not p.is_absolute():
            p = ROOT / p
        return p.expanduser().resolve()

    def resolve_db(self) -> Path:
        raw = (self.database_path or "").strip()
        p = Path(raw) if raw else (ROOT / "data" / "bot.db")
        if not p.is_absolute():
            p = ROOT / p
        return p.expanduser().resolve()


def get_settings() -> Settings:
    return Settings()
