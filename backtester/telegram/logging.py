"""Logging helpers that keep credentials out of worker logs."""
from __future__ import annotations

import logging
import re


class SensitiveDataFilter(logging.Filter):
    """Redact credentials from rendered log messages before handlers emit them."""

    _patterns = (
        (re.compile(r"(https://api\.telegram\.org/bot)[^/\s]+(/)", re.IGNORECASE), r"\1***REDACTED***\2"),
        (re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{10,}\b"), "***REDACTED***"),
        (re.compile(r"\b(ALPACA_API_KEY|ALPACA_SECRET_KEY|TWELVE_DATA_API_KEY)(\s*[=:]\s*)[^\s,;]+", re.IGNORECASE), r"\1\2***REDACTED***"),
        (re.compile(r"(Authorization(?:\s*header)?\s*[=:]\s*)(?:Bearer\s+)?[^\s,;]+", re.IGNORECASE), r"\1***REDACTED***"),
    )

    @classmethod
    def redact(cls, text: str) -> str:
        for pattern, replacement in cls._patterns:
            text = pattern.sub(replacement, text)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    """Redact values included in exception tracebacks as well as log messages."""

    def format(self, record: logging.LogRecord) -> str:
        return SensitiveDataFilter.redact(super().format(record))


def configure_worker_logging() -> None:
    """Configure worker logging without allowing HTTP client URL secrets through."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(item, SensitiveDataFilter) for item in handler.filters):
            handler.addFilter(SensitiveDataFilter())
        formatter = handler.formatter
        handler.setFormatter(RedactingFormatter(
            formatter._style._fmt if formatter else "%(message)s",
            datefmt=formatter.datefmt if formatter else None,
        ))
