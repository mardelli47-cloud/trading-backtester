"""In-memory broker used by tests and dashboard demos; never touches a network."""
from __future__ import annotations
from decimal import Decimal
from .base import Account, Order, OrderRequest, OrderStatus, Position
class MockBroker:
    def __init__(self, equity: Decimal=Decimal("10000"), buying_power: Decimal=Decimal("10000")):
        self.account=Account(equity, buying_power, buying_power); self.positions: list[Position]=[]; self.orders: list[Order]=[]; self.reject_next=False
    def get_account(self): return self.account
    def list_positions(self): return list(self.positions)
    def list_orders(self, open_only=True): return [o for o in self.orders if not open_only or o.status in {OrderStatus.SUBMITTED,OrderStatus.ACCEPTED,OrderStatus.PARTIALLY_FILLED}]
    def submit_order(self, request: OrderRequest):
        status=OrderStatus.REJECTED if self.reject_next else OrderStatus.ACCEPTED; self.reject_next=False
        order=Order(str(len(self.orders)+1), request.client_order_id, request.symbol, request.side, request.qty, request.order_type, status, request.limit_price, "mock rejection" if status is OrderStatus.REJECTED else None)
        self.orders.append(order); return order
