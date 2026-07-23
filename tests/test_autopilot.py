from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from backtester.autopilot import Autopilot, AutopilotState, MarketSnapshot
from backtester.broker import MockBroker
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings

NOW = datetime(2026, 1, 5, 15, 0, tzinfo=timezone.utc)
def autopilot(tmp_path):
    b = MockBroker(); s = PaperOrderService(b, RiskManager(RiskSettings(), b.account.equity), False)
    return Autopilot(s, tmp_path / "state.json"), b
def snapshot(**changes):
    base = dict(symbol="AAPL", timestamp=NOW, close=Decimal("100"), bid=Decimal("99.95"), ask=Decimal("100.05"), daily_volume=1_000_000, atr=Decimal("2"), vwap=Decimal("99"), trend_up=True, momentum_up=True, relative_strength=Decimal("1"), relative_volume=Decimal("2"), breakout=True)
    base.update(changes); return MarketSnapshot(**base)
def test_restart_never_reactivates_paper(tmp_path):
    a, _ = autopilot(tmp_path); a.shadow_closed = 50; a.transition(AutopilotState.PAPER_ACTIVE)
    restored, _ = autopilot(tmp_path)
    assert restored.state is AutopilotState.PAUSED
def test_two_confirmations_start_shadow_and_no_broker_order(tmp_path):
    a, b = autopilot(tmp_path)
    assert "Erste" in a.start() and a.state is AutopilotState.DISABLED
    assert a.start().startswith("Shadow") and a.state is AutopilotState.SHADOW
    plans = a.scan([snapshot()], NOW); assert len(plans) == 1
    assert a.execute(plans[0], NOW) == "shadow" and not b.orders
def test_stale_or_duplicate_candle_cannot_trade(tmp_path):
    a, _ = autopilot(tmp_path); a.start(); a.start()
    assert not a.scan([snapshot(timestamp=NOW-timedelta(seconds=91))], NOW)
    assert len(a.scan([snapshot()], NOW)) == 1
    assert not a.scan([snapshot()], NOW)
def test_scanner_rejects_nonclosed_bad_spread_and_otc(tmp_path):
    a, _ = autopilot(tmp_path); a.start(); a.start()
    assert not a.scan([snapshot(is_closed=False)], NOW)
    assert not a.scan([snapshot(symbol="MSFT", bid=Decimal("90"), ask=Decimal("110"))], NOW)
    assert not a.scan([snapshot(symbol="IBM", exchange="OTC")], NOW)
def test_size_and_paper_gate_are_risk_limited(tmp_path):
    a, b = autopilot(tmp_path)
    assert a.position_size(Decimal("100"), Decimal("99")) == Decimal("20")
    a.shadow_closed = 50; a.transition(AutopilotState.PAPER_ACTIVE)
    plan = a.scan([snapshot()], NOW)[0]; a.execute(plan, NOW)
    assert b.orders and b.orders[0].side == "buy"
def test_paper_requires_shadow_evidence_and_emergency_locks(tmp_path):
    a, _ = autopilot(tmp_path)
    with pytest.raises(ValueError, match="Shadow"): a.transition(AutopilotState.PAPER_ACTIVE)
    a.emergency()
    assert a.state is AutopilotState.EMERGENCY_STOP and a.service.risk.kill_switch
