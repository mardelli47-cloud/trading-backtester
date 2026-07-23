"""Environment-only configuration for the Telegram paper-trading worker."""
from __future__ import annotations
from dataclasses import dataclass
import os
import re

@dataclass(frozen=True)
class TelegramSettings:
    token: str
    allowed_user_ids: frozenset[int]
    webhook_url: str = ""
    webhook_secret: str = ""
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = True
    alpaca_data_feed: str = "iex"

    @staticmethod
    def parse_allowed_user_ids(raw: str) -> frozenset[int]:
        cleaned = raw.strip().strip("[]").replace('"', "").replace("'", "")
        values = [value.strip() for value in cleaned.split(",") if value.strip()]
        if not values or any(not re.fullmatch(r"[0-9]+", value) for value in values):
            raise ValueError("TELEGRAM_ALLOWED_USER_IDS muss gültige numerische Benutzer-IDs enthalten.")
        return frozenset(int(value) for value in values)

    @classmethod
    def from_env(cls) -> "TelegramSettings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN fehlt.")
        raw_ids = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
        ids = cls.parse_allowed_user_ids(raw_ids)
        if not ids:
            raise ValueError("TELEGRAM_ALLOWED_USER_IDS fehlt oder ist leer.")
        paper = os.getenv("ALPACA_PAPER", "").lower() == "true"
        if not paper:
            raise ValueError("ALPACA_PAPER muss exakt true sein; Echtgeldhandel ist deaktiviert.")
        return cls(token, ids, os.getenv("TELEGRAM_WEBHOOK_URL", "").rstrip("/"),
                   os.getenv("TELEGRAM_WEBHOOK_SECRET", ""), os.getenv("ALPACA_API_KEY", ""),
                   os.getenv("ALPACA_SECRET_KEY", ""), paper, os.getenv("ALPACA_DATA_FEED", "iex").lower())
