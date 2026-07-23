from __future__ import annotations
from decimal import Decimal
from uuid import uuid4

def signal_message(signal: dict[str, object]) -> str:
    return ("📊 *Handelssignal*\n"
            f"Symbol: `{signal['symbol']}`\nKurs: {signal['price']}\nStrategie: {signal['strategy']}\n"
            f"Richtung: {signal['side']} | Stärke: {signal['strength']}\nZeit: {signal['timestamp']}\n"
            f"Vorschlag: {signal['qty']} Stück\nStop-Loss: {signal['stop_loss']}\n"
            f"Take-Profit: {signal['take_profit']}\nChance-Risiko: {signal['risk_reward']}\n\n"
            "⚠️ *PAPER TRADING – KEIN ECHTGELD*")

def error_id() -> str:
    """Return a short correlation ID that is safe to disclose to Telegram users."""
    return uuid4().hex[:6].upper()


def safe_error(_: Exception, incident_id: str | None = None) -> str:
    """Never expose upstream exception text, which might contain credentials."""
    return f"⚠️ Die Funktion konnte nicht ausgeführt werden. Fehler-ID: {incident_id or error_id()}."
