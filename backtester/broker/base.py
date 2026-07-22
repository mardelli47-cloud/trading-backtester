"""Broker-neutral paper-trading data types and interface."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol

class OrderStatus(str, Enum):
    SUBMITTED="submitted"; ACCEPTED="accepted"; PARTIALLY_FILLED="partially_filled"; FILLED="filled"; CANCELED="canceled"; REJECTED="rejected"

@dataclass(frozen=True)
class Account:
    equity: Decimal; buying_power: Decimal; cash: Decimal
@dataclass(frozen=True)
class Position:
    symbol: str; qty: Decimal; market_value: Decimal; unrealized_pl: Decimal
@dataclass(frozen=True)
class Order:
    id: str; client_order_id: str; symbol: str; side: str; qty: Decimal; order_type: str; status: OrderStatus; limit_price: Decimal|None=None; rejection_reason: str|None=None
@dataclass(frozen=True)
class OrderRequest:
    symbol: str; side: str; qty: Decimal; order_type: str="market"; limit_price: Decimal|None=None; client_order_id: str=""

class Broker(Protocol):
    def get_account(self) -> Account: ...
    def list_positions(self) -> list[Position]: ...
    def list_orders(self, open_only: bool=True) -> list[Order]: ...
    def submit_order(self, request: OrderRequest) -> Order: ...
