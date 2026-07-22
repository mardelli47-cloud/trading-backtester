from datetime import datetime, timezone
from decimal import Decimal
import pytest
from backtester.broker import MockBroker, OrderRequest, OrderStatus
from backtester.execution import PaperOrderService
from backtester.live import ClosedBarAnalyzer, AlpacaMarketDataStream
from backtester.risk import RiskManager, RiskSettings
NOW=datetime(2026,1,5,15,0,tzinfo=timezone.utc) # 10:00 ET

def service(broker=None, enabled=True, settings=RiskSettings(), kill=False):
    broker=broker or MockBroker()
    return PaperOrderService(broker,RiskManager(settings,broker.get_account().equity,kill),enabled),broker

def request(qty="1", cid="one"): return OrderRequest("AAPL","buy",Decimal(qty),client_order_id=cid)
def test_no_order_without_explicit_paper_trading():
    s,b=service(enabled=False)
    with pytest.raises(PermissionError): s.submit(request(),Decimal("100"),NOW)
    assert not b.orders
def test_no_order_without_api_keys():
    s=PaperOrderService(None,RiskManager(RiskSettings(),Decimal("10000")),True)
    with pytest.raises(RuntimeError,match="API-Schlüssel"): s.submit(request(),Decimal("100"),NOW)
def test_duplicate_order_is_blocked():
    s,b=service(); s.submit(request(),Decimal("100"),NOW)
    with pytest.raises(ValueError,match="Doppelte"): s.submit(request(),Decimal("100"),NOW)
def test_daily_loss_limit_blocks_order():
    s,b=service(settings=RiskSettings(max_daily_loss_pct=Decimal("3"))); s.risk.day_start_equity=Decimal("10000"); b.account=b.account.__class__(Decimal("9600"),Decimal("10000"),Decimal("10000"))
    with pytest.raises(ValueError,match="Tagesverlustlimit"): s.submit(request(),Decimal("100"),NOW)
def test_position_limit_and_invalid_size():
    s,_=service(settings=RiskSettings(max_position_qty=Decimal("2")))
    with pytest.raises(ValueError,match="Maximale Positionsgröße"): s.submit(request("3"),Decimal("100"),NOW)
    with pytest.raises(ValueError,match="Ordergröße"): s.submit(request("0"),Decimal("100"),NOW)
def test_rejected_order_is_visible():
    s,b=service(); b.reject_next=True; order=s.submit(request(),Decimal("100"),NOW)
    assert order.status is OrderStatus.REJECTED and s.rejections
def test_market_hours_and_kill_switch():
    s,_=service(kill=True)
    with pytest.raises(ValueError,match="Kill Switch"): s.submit(request(),Decimal("100"),NOW)
def test_closed_bar_lookahead_protection():
    analyzer=ClosedBarAnalyzer("Momentum")
    bar={"timestamp":"2026-01-01T10:00:00Z","open":100,"high":999,"low":1,"close":999,"volume":1,"is_closed":False}
    assert analyzer.add_closed_bar("AAPL",bar) is None
    assert "AAPL" not in analyzer._bars
def test_stream_disconnect_sets_error_without_network():
    stream=AlpacaMarketDataStream(["AAPL"],lambda _:None,api_key="",secret_key="")
    stream.run_forever(max_retries=0)
    assert not stream.connected and stream.error
def test_stop_loss_and_take_profit_are_detected():
    risk=RiskManager(RiskSettings(stop_loss_pct=Decimal("1"),take_profit_pct=Decimal("2")),Decimal("10000"))
    assert risk.protective_exit_reason(Decimal("100"),Decimal("98.99"),"buy") == "stop_loss"
    assert risk.protective_exit_reason(Decimal("100"),Decimal("102"),"buy") == "take_profit"
