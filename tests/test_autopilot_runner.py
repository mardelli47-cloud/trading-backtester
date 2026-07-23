from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, MagicMock
import pytest
from backtester.autopilot import Autopilot, AutopilotState, TradePlan
from backtester.autopilot_runner import AutopilotRunner
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings

class Broker:
    def get_account(self): return type('A', (), {'equity': Decimal('10000'), 'buying_power': Decimal('10000')})()
    def list_positions(self): return []
    def list_orders(self, *a): return []

def make(tmp_path):
    ap = Autopilot(PaperOrderService(Broker(), RiskManager(RiskSettings(), Decimal('10000'))), tmp_path/'state.json')
    return ap, AutopilotRunner(ap, Mock(), symbols='AAPL', interval_seconds=1)

def plan(): return TradePlan('AAPL', 'confirmed_breakout', Decimal('10'), Decimal('9'), Decimal('12'), Decimal('5'), 'AAPL:2026-01-01T00:00:00+00:00')

def test_disabled_runner_does_not_build_snapshots(tmp_path):
    ap, runner = make(tmp_path); runner.run_cycle(); runner.market_data.get_market_clock.assert_not_called()

def test_shadow_stop_closes_exactly_once(tmp_path):
    ap, runner = make(tmp_path); ap.transition(AutopilotState.SHADOW); ap.execute(plan())
    frame = MagicMock(); frame.iloc.__getitem__.return_value = type('B', (), {'low': 8, 'high': 13, 'close': 10})()
    runner.market_data.get_intraday_bars.return_value = frame
    runner.monitor_open_plans(datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)); runner.monitor_open_plans(datetime(2026, 1, 1, 0, 3, tzinfo=timezone.utc))
    assert ap.shadow_closed == 1 and ap.shadow_results[0]['reason'] == 'stop'

def test_paper_activation_needs_two_confirmations_and_shadow_threshold(tmp_path, monkeypatch):
    ap, _ = make(tmp_path); monkeypatch.setenv('ALPACA_PAPER', 'true')
    with pytest.raises(ValueError): ap.activate_paper()
    ap.shadow_closed = ap.config.min_shadow_trades
    assert 'Erste' in ap.activate_paper(); assert ap.activate_paper().startswith('Paper-Autopilot')
