"""Environment-only configuration for the Telegram paper-trading worker."""
from __future__ import annotations
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class TelegramSettings:
    token: str
    allowed_user_ids: frozenset[int]
    webhook_url: str = ""
    webhook_secret: str = ""
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True

    @classmethod
    def from_env(cls) -> "TelegramSettings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN fehlt.")
        raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
        try:
            ids = frozenset(int(value.strip()) for value in raw_ids.split(",") if value.strip())
        except ValueError as exc:
            raise ValueError("TELEGRAM_ALLOWED_USER_IDS muss kommagetrennte Zahlen enthalten.") from exc
        if not ids:
            raise ValueError("TELEGRAM_ALLOWED_USER_IDS fehlt oder ist leer.")
        paper = os.getenv("ALPACA_PAPER", "").lower() == "true"
        if not paper:
            raise ValueError("ALPACA_PAPER muss exakt true sein; Echtgeldhandel ist deaktiviert.")
        return cls(token, ids, os.getenv("TELEGRAM_WEBHOOK_URL", "").rstrip("/"),
                   os.getenv("TELEGRAM_WEBHOOK_SECRET", ""), os.getenv("ALPACA_API_KEY", ""),
                   os.getenv("ALPACA_SECRET_KEY", ""), paper)
