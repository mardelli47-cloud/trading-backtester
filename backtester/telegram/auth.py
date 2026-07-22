from __future__ import annotations
from collections import defaultdict, deque
from time import monotonic

class AccessControl:
    """Whitelist plus in-memory sliding-window command limiter."""
    def __init__(self, allowed_user_ids: frozenset[int], limit: int = 20, window_seconds: int = 60):
        self.allowed = allowed_user_ids; self.limit = limit; self.window = window_seconds; self._calls = defaultdict(deque)
    def allowed_now(self, user_id: int, now: float | None = None) -> bool:
        if user_id not in self.allowed: return False
        now = monotonic() if now is None else now; calls = self._calls[user_id]
        while calls and now - calls[0] >= self.window: calls.popleft()
        if len(calls) >= self.limit: return False
        calls.append(now); return True
