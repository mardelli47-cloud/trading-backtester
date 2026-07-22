from __future__ import annotations
from decimal import Decimal

def signal_message(signal: dict[str, object]) -> str:
    return ("📊 *Handelssignal*\n"
            f"Symbol: `{signal['symbol']}`\nKurs: {signal['price']}\nStrategie: {signal['strategy']}\n"
            f"Richtung: {signal['side']} | Stärke: {signal['strength']}\nZeit: {signal['timestamp']}\n"
            f"Vorschlag: {signal['qty']} Stück\nStop-Loss: {signal['stop_loss']}\n"
            f"Take-Profit: {signal['take_profit']}\nChance-Risiko: {signal['risk_reward']}\n\n"
            "⚠️ *PAPER TRADING – KEIN ECHTGELD*")

def safe_error(_: Exception) -> str:
    """Never expose upstream exception text, which might contain credentials."""
    return "Die Anfrage konnte nicht verarbeitet werden. Details wurden nicht übertragen."
