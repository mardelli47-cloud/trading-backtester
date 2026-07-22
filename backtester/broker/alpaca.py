"""Thin, paper-only adapter around the official alpaca-py SDK."""
from __future__ import annotations
import os
from decimal import Decimal
from .base import Account, Broker, Order, OrderRequest, OrderStatus, Position
class AlpacaPaperBroker(Broker):
    def __init__(self, api_key: str|None=None, secret_key: str|None=None, paper: bool=True):
        if not paper:
            raise ValueError("Live-Trading ist absichtlich deaktiviert; nur Paper Trading wird unterstützt.")
        self.api_key=api_key or os.getenv("ALPACA_API_KEY", ""); self.secret_key=secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        if not self.api_key or not self.secret_key: raise ValueError("Alpaca API-Schlüssel fehlen. Setze ALPACA_API_KEY und ALPACA_SECRET_KEY als Umgebungsvariablen.")
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc: raise RuntimeError("alpaca-py ist nicht installiert.") from exc
        self.client=TradingClient(self.api_key, self.secret_key, paper=True)
    @staticmethod
    def _status(value: object)->OrderStatus:
        try: return OrderStatus(str(value))
        except ValueError: return OrderStatus.REJECTED
    def get_account(self):
        a=self.client.get_account(); return Account(Decimal(str(a.equity)),Decimal(str(a.buying_power)),Decimal(str(a.cash)))
    def list_positions(self):
        return [Position(p.symbol,Decimal(str(p.qty)),Decimal(str(p.market_value)),Decimal(str(p.unrealized_pl))) for p in self.client.get_all_positions()]
    def list_orders(self, open_only=True):
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        status=QueryOrderStatus.OPEN if open_only else QueryOrderStatus.ALL
        return [self._to_order(o) for o in self.client.get_orders(filter=GetOrdersRequest(status=status))]
    def _to_order(self,o): return Order(str(o.id),str(o.client_order_id),o.symbol,str(o.side).lower(),Decimal(str(o.qty)),str(o.type).lower(),self._status(o.status),Decimal(str(o.limit_price)) if o.limit_price else None, getattr(o,"rejected_reason",None))
    def submit_order(self, request):
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        common=dict(symbol=request.symbol, qty=float(request.qty), side=OrderSide(request.side), time_in_force=TimeInForce.DAY, client_order_id=request.client_order_id)
        payload=LimitOrderRequest(**common,limit_price=float(request.limit_price)) if request.order_type=="limit" else MarketOrderRequest(**common)
        return self._to_order(self.client.submit_order(order_data=payload))
