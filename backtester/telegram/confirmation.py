from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from backtester.broker.base import OrderRequest

@dataclass
class PendingOrder:
    request: OrderRequest; price: object; user_id: int; expires_at: datetime; confirmed: bool = False

class OrderConfirmations:
    """Two distinct clicks are required; completed/expired IDs cannot be reused."""
    def __init__(self, ttl_seconds: int = 60): self.ttl = ttl_seconds; self._pending: dict[str, PendingOrder] = {}; self._used: set[str] = set()
    def create(self, request: OrderRequest, price: object, user_id: int, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc); token = uuid4().hex
        self._pending[token] = PendingOrder(request, price, user_id, now + timedelta(seconds=self.ttl)); return token
    def confirm(self, token: str, user_id: int, now: datetime | None = None) -> OrderRequest | None:
        now = now or datetime.now(timezone.utc); pending = self._pending.get(token)
        if token in self._used or not pending or pending.user_id != user_id or now >= pending.expires_at: self._pending.pop(token, None); return None
        if not pending.confirmed: pending.confirmed = True; return None
        self._pending.pop(token); self._used.add(token); return pending.request
    def reject(self, token: str, user_id: int) -> bool:
        pending = self._pending.get(token)
        if not pending or pending.user_id != user_id: return False
        self._pending.pop(token); self._used.add(token); return True
