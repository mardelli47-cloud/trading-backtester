from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from backtester.broker.base import Account, OrderRequest, Position
@dataclass(frozen=True)
class RiskSettings:
    max_risk_per_trade_pct: Decimal=Decimal("1"); max_position_qty: Decimal=Decimal("100"); max_open_positions: int=5; max_daily_loss_pct: Decimal=Decimal("3"); stop_loss_pct: Decimal=Decimal("1"); take_profit_pct: Decimal=Decimal("2"); trailing_stop_pct: Decimal|None=None; cooldown_minutes: int=0
class RiskManager:
    def __init__(self, settings: RiskSettings, day_start_equity: Decimal, kill_switch: bool=False): self.settings=settings; self.day_start_equity=day_start_equity; self.kill_switch=kill_switch; self.last_loss_at: datetime|None=None
    def validate(self, request: OrderRequest, account: Account, positions: list[Position], open_orders: list[object], price: Decimal, now: datetime|None=None)->str|None:
        now=now or datetime.now(timezone.utc)
        if self.kill_switch: return "Kill Switch ist aktiv."
        if request.qty <= 0 or request.qty != request.qty.to_integral_value(): return "Ordergröße muss eine positive ganze Zahl sein."
        if request.qty > self.settings.max_position_qty: return "Maximale Positionsgröße überschritten."
        if request.side not in {"buy","sell"} or request.order_type not in {"market","limit"}: return "Ungültige Orderparameter."
        if request.order_type=="limit" and (request.limit_price is None or request.limit_price<=0): return "Limitpreis muss positiv sein."
        if account.equity <= self.day_start_equity*(Decimal("1")-self.settings.max_daily_loss_pct/100): return "Tagesverlustlimit erreicht."
        if len(positions)>=self.settings.max_open_positions and not any(p.symbol==request.symbol for p in positions): return "Maximale Anzahl gleichzeitiger Positionen erreicht."
        if request.qty*price > account.buying_power and request.side=="buy": return "Kaufkraft reicht nicht aus."
        if self.last_loss_at and now-self.last_loss_at < timedelta(minutes=self.settings.cooldown_minutes): return "Cooldown nach Verlusttrade aktiv."
        return None
    def protective_exit_reason(self, entry_price: Decimal, current_price: Decimal, side: str, peak_price: Decimal|None=None) -> str|None:
        """Return a protective exit reason without placing or modifying an order."""
        if entry_price <= 0 or current_price <= 0:
            raise ValueError("Preise für Stop-Loss-Prüfung müssen positiv sein.")
        direction = Decimal("1") if side == "buy" else Decimal("-1")
        change = direction * (current_price / entry_price - Decimal("1")) * 100
        if change <= -self.settings.stop_loss_pct:
            return "stop_loss"
        if change >= self.settings.take_profit_pct:
            return "take_profit"
        if self.settings.trailing_stop_pct is not None and peak_price is not None:
            drawdown = direction * (current_price / peak_price - Decimal("1")) * 100
            if drawdown <= -self.settings.trailing_stop_pct:
                return "trailing_stop"
        return None
    def record_loss(self, when: datetime|None=None): self.last_loss_at=when or datetime.now(timezone.utc)
