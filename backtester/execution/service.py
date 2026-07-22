"""Fail-closed paper order submission with idempotency protection."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo
from backtester.broker.base import Broker, Order, OrderRequest
from backtester.risk import RiskManager
class PaperOrderService:
    def __init__(self, broker: Broker|None, risk: RiskManager, paper_enabled: bool=False): self.broker=broker; self.risk=risk; self.paper_enabled=paper_enabled; self._submitted_ids:set[str]=set(); self.rejections:list[str]=[]
    @staticmethod
    def market_is_open(now: datetime|None=None)->bool:
        current=(now or datetime.now(ZoneInfo("America/New_York"))).astimezone(ZoneInfo("America/New_York"))
        return current.weekday()<5 and time(9,30)<=current.time()<time(16,0)
    def submit(self, request: OrderRequest, price: Decimal, now: datetime|None=None)->Order:
        if not self.paper_enabled: raise PermissionError("Paper Trading wurde nicht ausdrücklich im Dashboard aktiviert.")
        if self.broker is None: raise RuntimeError("Kein Paper-Broker konfiguriert; API-Schlüssel fehlen.")
        if not self.market_is_open(now): raise ValueError("Neue Orders sind außerhalb der Handelszeiten gesperrt.")
        client_id=request.client_order_id or f"paper-{uuid4().hex}"
        if client_id in self._submitted_ids or any(o.client_order_id==client_id for o in self.broker.list_orders(False)): raise ValueError("Doppelte Order durch Idempotenzschutz verhindert.")
        positions=self.broker.list_positions(); open_orders=self.broker.list_orders(True)
        if any(o.symbol==request.symbol for o in open_orders): raise ValueError("Für dieses Symbol existiert bereits eine offene Order.")
        reason=self.risk.validate(replace(request,client_order_id=client_id),self.broker.get_account(),positions,open_orders,price,now)
        if reason: raise ValueError(reason)
        # Mark before network call: a timeout must never be retried blindly.
        self._submitted_ids.add(client_id)
        try: order=self.broker.submit_order(replace(request,client_order_id=client_id))
        except Exception as exc: raise RuntimeError("Orderstatus unbekannt nach Netzwerkfehler; keine automatische Wiederholung.") from exc
        if order.status.value=="rejected": self.rejections.append(order.rejection_reason or "Order abgelehnt")
        return order
