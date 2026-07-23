"""Fail-closed, paper-only autopilot domain model.

This module deliberately separates deterministic setup selection from broker IO.
It never creates a live client and defaults to ``DISABLED`` after a process
restart.  A scheduler may call :meth:`Autopilot.scan`; it must supply a
closed, current market snapshot.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from enum import Enum
import json
from pathlib import Path
import os
from typing import Iterable

from backtester.broker.base import OrderRequest
from backtester.execution import PaperOrderService


class AutopilotState(str, Enum):
    DISABLED = "DISABLED"; SHADOW = "SHADOW"; PAPER_ACTIVE = "PAPER_ACTIVE"
    PAUSED = "PAUSED"; RISK_LOCKED = "RISK_LOCKED"; EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass(frozen=True)
class AutopilotConfig:
    risk_per_trade_pct: Decimal = Decimal("0.25")
    max_open_positions: int = 3
    max_position_equity_pct: Decimal = Decimal("20")
    max_total_exposure_pct: Decimal = Decimal("50")
    max_new_trades_per_day: int = 5
    min_reward_risk: Decimal = Decimal("2")
    min_price: Decimal = Decimal("5")
    min_daily_volume: int = 500_000
    max_spread_pct: Decimal = Decimal("0.25")
    min_score: Decimal = Decimal("7")
    max_data_age_seconds: int = 90
    min_shadow_trades: int = 20
    max_daily_loss_pct: Decimal = Decimal("2")


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str; timestamp: datetime; close: Decimal; bid: Decimal; ask: Decimal
    daily_volume: int; atr: Decimal; vwap: Decimal; trend_up: bool; momentum_up: bool
    relative_strength: Decimal; relative_volume: Decimal; breakout: bool = False
    pullback: bool = False; is_closed: bool = True; asset_class: str = "stock"
    exchange: str = "NYSE"; market_open: bool = True

    @property
    def spread_pct(self) -> Decimal:
        return (self.ask - self.bid) / self.close * 100 if self.close > 0 else Decimal("999")


@dataclass(frozen=True)
class TradePlan:
    symbol: str; strategy: str; entry: Decimal; stop: Decimal; target: Decimal; qty: Decimal; candle_id: str


class Autopilot:
    """Persistent safety state and deterministic long-only decision gate."""
    def __init__(self, service: PaperOrderService, path: str | Path = "autopilot_state.json", config: AutopilotConfig = AutopilotConfig()):
        self.service, self.path, self.config = service, Path(path), config
        self.state = AutopilotState.DISABLED
        self.processed_candles: set[str] = set(); self.open_plans: dict[str, TradePlan] = {}
        self.order_ids: dict[str, str] = {}; self.last_signals: dict[str, str] = {}
        self.new_trades_today = 0; self.shadow_closed = 0; self.critical_errors = 0; self.shadow_results: list[dict[str, str]] = []
        self._pending_start = False; self._pending_paper = False
        configured_min = int(os.getenv("AUTOPILOT_MIN_SHADOW_TRADES", str(self.config.min_shadow_trades)))
        if configured_min < 5: configured_min = 5
        self.config = AutopilotConfig(**{**asdict(self.config), "min_shadow_trades": configured_min})
        self.load()
        # Never resume trading due to a restart, even if persisted state was active.
        if self.state is AutopilotState.PAPER_ACTIVE:
            self.state = AutopilotState.PAUSED
            self.service.paper_enabled = False
            self.save()

    def save(self) -> None:
        payload = {"state": self.state.value, "processed_candles": sorted(self.processed_candles),
                   "open_plans": {k: {**asdict(v), "entry": str(v.entry), "stop": str(v.stop), "target": str(v.target), "qty": str(v.qty)} for k,v in self.open_plans.items()},
                   "order_ids": self.order_ids, "last_signals": self.last_signals,
                   "new_trades_today": self.new_trades_today, "shadow_closed": self.shadow_closed, "critical_errors": self.critical_errors, "shadow_results": self.shadow_results}
        self.path.parent.mkdir(parents=True, exist_ok=True); self.path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    def load(self) -> None:
        if not self.path.exists(): return
        data = json.loads(self.path.read_text(encoding="utf-8")); self.state = AutopilotState(data.get("state", "DISABLED"))
        self.processed_candles = set(data.get("processed_candles", [])); self.order_ids = data.get("order_ids", {}); self.last_signals = data.get("last_signals", {})
        self.new_trades_today = data.get("new_trades_today", 0); self.shadow_closed = data.get("shadow_closed", 0); self.critical_errors = data.get("critical_errors", 0); self.shadow_results = data.get("shadow_results", [])
        self.open_plans = {symbol: TradePlan(symbol, item["strategy"], Decimal(item["entry"]), Decimal(item["stop"]), Decimal(item["target"]), Decimal(item["qty"]), item["candle_id"]) for symbol, item in data.get("open_plans", {}).items()}

    def transition(self, target: AutopilotState, *, override_shadow: bool = False) -> None:
        if target is AutopilotState.PAPER_ACTIVE and self.shadow_closed < self.config.min_shadow_trades and not override_shadow:
            raise ValueError(f"Paper-Modus gesperrt: mindestens {self.config.min_shadow_trades} abgeschlossene Shadow-Trades erforderlich.")
        if self.state in {AutopilotState.RISK_LOCKED, AutopilotState.EMERGENCY_STOP} and target is AutopilotState.PAPER_ACTIVE:
            raise ValueError("Risk Lock/Kill Switch erfordert eine manuelle Sicherheitsprüfung.")
        self.state = target; self.service.paper_enabled = target is AutopilotState.PAPER_ACTIVE; self.save()

    def start(self) -> str:
        if not self._pending_start: self._pending_start = True; return "Erste Bestätigung gespeichert. Wiederhole /autopilot start innerhalb dieser Sitzung."
        self._pending_start = False; self.transition(AutopilotState.SHADOW); return "Shadow-Autopilot gestartet; es werden keine Brokerorders gesendet."

    def activate_paper(self) -> str:
        if self.shadow_closed < self.config.min_shadow_trades: raise ValueError(f"Paper-Modus gesperrt: mindestens {self.config.min_shadow_trades} abgeschlossene Shadow-Trades erforderlich.")
        if self.service.risk.kill_switch: raise ValueError("Kill Switch aktiv.")
        if os.getenv("ALPACA_PAPER", "true").lower() != "true": raise ValueError("ALPACA_PAPER=false blockiert die Aktivierung.")
        if not self._pending_paper:
            self._pending_paper = True; return "Erste Paper-Bestätigung gespeichert. Wiederhole /autopilot paper."
        self._pending_paper = False; self.transition(AutopilotState.PAPER_ACTIVE); return "Paper-Autopilot aktiviert (nur Alpaca Paper)."

    def lock(self, reason: str) -> None:
        self.state = AutopilotState.RISK_LOCKED; self.service.paper_enabled = False; self.critical_errors += 1; self.last_signals["risk_lock"] = reason; self.save()

    def emergency(self) -> None:
        self.state = AutopilotState.EMERGENCY_STOP; self.service.paper_enabled = False; self.service.risk.kill_switch = True; self.save()

    def scan(self, snapshots: Iterable[MarketSnapshot], now: datetime | None = None) -> list[TradePlan]:
        """Return eligible plans only; reject stale/incomplete data before any IO."""
        now = now or datetime.now(timezone.utc); plans: list[TradePlan] = []
        if self.state not in {AutopilotState.SHADOW, AutopilotState.PAPER_ACTIVE}: return plans
        for s in snapshots:
            candle_id = f"{s.symbol}:{s.timestamp.isoformat()}"
            if candle_id in self.processed_candles: continue
            self.processed_candles.add(candle_id)
            if not self._valid(s, now): self.last_signals[s.symbol] = "abgelehnt: Daten/Marktfilter"; continue
            strategy = "confirmed_breakout" if s.breakout else "trend_pullback" if s.pullback else ""
            if not strategy: self.last_signals[s.symbol] = "kein bestätigtes Setup"; continue
            stop = s.close - max(s.atr, Decimal("0.01")); target = s.close + (s.close - stop) * self.config.min_reward_risk
            qty = self.position_size(s.close, stop)
            if qty <= 0: self.last_signals[s.symbol] = "abgelehnt: Positionsrisiko"; continue
            plan = TradePlan(s.symbol, strategy, s.ask, stop, target, qty, candle_id)
            self.last_signals[s.symbol] = f"{strategy}: Score erfüllt"; plans.append(plan)
        self.save(); return plans

    def _valid(self, s: MarketSnapshot, now: datetime) -> bool:
        age = now - s.timestamp if s.timestamp.tzinfo is not None else timedelta.max
        return (s.is_closed and s.market_open and s.asset_class in {"stock", "etf"} and s.exchange != "OTC" and s.close >= self.config.min_price and s.daily_volume >= self.config.min_daily_volume and s.spread_pct <= self.config.max_spread_pct and timedelta(0) <= age <= timedelta(seconds=self.config.max_data_age_seconds) and s.trend_up and s.momentum_up and s.relative_strength > 0 and s.relative_volume >= 1 and (s.breakout or s.pullback))

    def position_size(self, entry: Decimal, stop: Decimal) -> Decimal:
        if entry <= stop or entry <= 0: return Decimal("0")
        account = self.service.broker.get_account() if self.service.broker else None
        positions = self.service.broker.list_positions() if self.service.broker else []
        exposure = sum((p.market_value for p in positions), Decimal("0"))
        if not account or self.new_trades_today >= self.config.max_new_trades_per_day or len(positions) >= self.config.max_open_positions or exposure >= account.equity * self.config.max_total_exposure_pct / 100: return Decimal("0")
        risk_cash = account.equity * self.config.risk_per_trade_pct / 100
        qty = (risk_cash / (entry - stop)).to_integral_value(rounding=ROUND_DOWN)
        total_cap = (account.equity * self.config.max_total_exposure_pct / 100 - exposure) / entry
        cap = min(account.equity * self.config.max_position_equity_pct / 100 / entry, account.buying_power / entry, total_cap)
        return min(qty, cap.to_integral_value(rounding=ROUND_DOWN))

    def execute(self, plan: TradePlan, now: datetime | None = None) -> str:
        if plan.symbol in self.open_plans: self.lock("doppelte Order/Trade-Plan"); raise ValueError("Doppelte Order verhindert und Risk Lock aktiviert.")
        if self.state is AutopilotState.SHADOW:
            self.open_plans[plan.symbol] = plan; self.new_trades_today += 1; self.save(); return "shadow"
        if self.state is not AutopilotState.PAPER_ACTIVE: raise PermissionError("Autopilot ist nicht für Paper-Orders aktiviert.")
        order = self.service.submit(OrderRequest(plan.symbol, "buy", plan.qty, client_order_id=f"autopilot-{plan.candle_id}"), plan.entry, now)
        self.open_plans[plan.symbol] = plan; self.order_ids[plan.symbol] = order.id; self.new_trades_today += 1; self.save(); return order.id

    def close_shadow(self, symbol: str, exit_price: Decimal, reason: str, now: datetime | None = None) -> None:
        """Persist one virtual close; deleting first makes repeated monitoring idempotent."""
        plan = self.open_plans.pop(symbol, None)
        if plan is None: return
        risk = plan.entry - plan.stop
        pnl = (exit_price - plan.entry) * plan.qty
        self.shadow_results.append({"symbol": symbol, "exit": str(exit_price), "reason": reason, "pnl": str(pnl), "r_multiple": str((exit_price - plan.entry) / risk if risk else 0), "closed_at": (now or datetime.now(timezone.utc)).isoformat()})
        self.shadow_closed += 1; self.save()

    def status(self) -> str:
        return (f"Autopilot: {self.state.value}\nStrategien: Trend-Pullback, bestätigter Breakout (long-only)\n"
                f"Risiko/Trade: {self.config.risk_per_trade_pct}%; Positionen: max. {self.config.max_open_positions}; "
                f"Tagestrades: {self.new_trades_today}/{self.config.max_new_trades_per_day}; offene Shadow-Trades: {len(self.open_plans)}; abgeschlossene Shadow-Trades: {self.shadow_closed}/{self.config.min_shadow_trades}\n"
                "Paper Trading – kein echtes Geld. Reale Ausführungen können deutlich abweichen.")
