from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from backtester.broker import MockBroker, OrderRequest
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings
from backtester.telegram import OrderConfirmations, TelegramSettings
from backtester.telegram.bot import TelegramPaperController

NOW=datetime(2026,1,5,15,0,tzinfo=timezone.utc)
def controller(kill=False):
    broker=MockBroker(); service=PaperOrderService(broker, RiskManager(RiskSettings(),broker.get_account().equity,kill),True)
    return TelegramPaperController(service,frozenset({7})),broker
def request(): return OrderRequest("AAPL","buy",Decimal("1"),client_order_id="telegram-test")
def test_unauthorized_user_has_no_access():
    c,_=controller()
    with pytest.raises(PermissionError): c.propose(8,request(),Decimal("100"))
def test_missing_bot_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN",raising=False); monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS","7"); monkeypatch.setenv("ALPACA_PAPER","true")
    with pytest.raises(ValueError,match="BOT_TOKEN"): TelegramSettings.from_env()
def test_expired_confirmation():
    confirms=OrderConfirmations(); token=confirms.create(request(),Decimal("100"),7,NOW)
    assert confirms.confirm(token,7,NOW+timedelta(seconds=60)) is None
def test_duplicate_confirmation_only_submits_once():
    c,b=controller(); token=c.propose(7,request(),Decimal("100"))
    assert c.confirm(7,token) is None
    c.confirm(7,token); assert len(b.orders)==1
    assert c.confirm(7,token) is None and len(b.orders)==1
def test_kill_switch_blocks_confirmation():
    c,_=controller(); c.kill();
    with pytest.raises(ValueError,match="gestoppt"): c.propose(7,request(),Decimal("100"))
def test_disabled_paper_trading_is_rejected(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN","x"); monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS","7"); monkeypatch.setenv("ALPACA_PAPER","false")
    with pytest.raises(ValueError,match="ALPACA_PAPER"): TelegramSettings.from_env()
def test_missing_alpaca_keys_fails_before_network(monkeypatch):
    from backtester.broker import AlpacaPaperBroker
    monkeypatch.delenv("ALPACA_API_KEY",raising=False); monkeypatch.delenv("ALPACA_SECRET_KEY",raising=False)
    with pytest.raises(ValueError,match="Schlüssel"): AlpacaPaperBroker()
def test_network_error_is_not_retried():
    c,b=controller(); b.submit_order=lambda _: (_ for _ in ()).throw(OSError("offline"))
    token=c.propose(7,request(),Decimal("100")); c.confirm(7,token)
    with pytest.raises(RuntimeError,match="keine automatische Wiederholung"): c.confirm(7,token)
    assert c.confirm(7,token) is None
