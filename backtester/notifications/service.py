"""Safe Telegram notification gateway; it never logs secrets or raw exceptions."""
from __future__ import annotations
from collections.abc import Awaitable, Callable

class NotificationService:
    def __init__(self, send: Callable[[str], Awaitable[None]]): self._send = send
    async def notify(self, event: str, detail: str = "") -> None:
        labels = {"bar_closed":"Kursbalken abgeschlossen", "signal":"Neues Handelssignal", "order":"Paper-Order", "protective_exit":"Stop-Loss/Take-Profit ausgelöst", "daily_loss":"Tagesverlustlimit erreicht", "disconnected":"Alpaca-Verbindung getrennt", "reconnected":"Alpaca-Verbindung wiederhergestellt", "kill":"Kill Switch aktiviert"}
        await self._send(f"{labels.get(event, 'Status')}: {detail}\n⚠️ PAPER TRADING – KEIN ECHTGELD")
