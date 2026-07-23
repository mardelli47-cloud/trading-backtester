from datetime import datetime, timedelta, timezone
from decimal import Decimal
import asyncio
import logging
import pytest
from backtester.broker import MockBroker, OrderRequest
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings
from backtester.telegram import OrderConfirmations, TelegramSettings
from backtester.telegram.bot import COMMANDS, TelegramPaperController, build_application, run_worker

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
def test_alpaca_header_validation_identifies_only_source_environment_variable(monkeypatch, caplog):
    from backtester.broker import AlpacaPaperBroker
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("ALPACA_API_KEY", "valid-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "not-a-secret-ä")
    with pytest.raises(ValueError, match="ALPACA_SECRET_KEY") as exc_info:
        AlpacaPaperBroker()
    assert "not-a-secret" not in str(exc_info.value)
    assert "APCA-API-KEY-ID" in caplog.text
    assert "APCA-API-SECRET-KEY" in caplog.text
    assert "not-a-secret" not in caplog.text
def test_webhook_header_validation_identifies_only_source_environment_variable(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr("backtester.telegram.bot.build_application", lambda *_: pytest.fail("application must not be created"))
    with pytest.raises(ValueError, match="TELEGRAM_WEBHOOK_SECRET") as exc_info:
        run_worker(controller()[0], "token", "https://example.test", "secret-ä")
    assert "secret-" not in str(exc_info.value)
    assert "X-Telegram-Bot-Api-Secret-Token" in caplog.text
    assert "secret-" not in caplog.text
def test_webhook_binds_to_render_host_and_port(monkeypatch):
    calls = []
    class Application:
        def run_webhook(self, **kwargs): calls.append(kwargs)
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setattr("backtester.telegram.bot.build_application", lambda *_: Application())
    run_worker(controller()[0], "token", "https://bot.example")
    assert calls == [{
        "listen": "0.0.0.0", "port": 10000, "url_path": "telegram",
        "webhook_url": "https://bot.example/telegram", "secret_token": None,
    }]
def test_network_error_is_not_retried():
    c,b=controller(); b.submit_order=lambda _: (_ for _ in ()).throw(OSError("offline"))
    token=c.propose(7,request(),Decimal("100")); c.confirm(7,token)
    with pytest.raises(RuntimeError,match="keine automatische Wiederholung"): c.confirm(7,token)
    assert c.confirm(7,token) is None

def test_read_only_commands_return_their_respective_paper_data():
    c, _ = controller()
    assert "Analysemodus" in c.command_message("status")
    assert "abgeschlossenen Balken" in c.command_message("signals")
    assert "Offene Positionen" in c.command_message("positions")
    assert "Orders" in c.command_message("orders")
    assert "Paper-Konto" in c.command_message("account")
    assert "Risikolimits" in c.command_message("risk")
    assert c.command_message("watchlist", ("aapl,msft",)) == "Watchlist: AAPL, MSFT"
    assert "AAPL, MSFT" in c.command_message("signals")

def test_each_command_handler_dispatches_to_its_registered_command():
    c, _ = controller()
    app = build_application(c, "123:abc")
    handlers = [handler for handler in app.handlers[0] if hasattr(handler, "commands")]
    assert len(handlers) == len(COMMANDS)

    class Message:
        def __init__(self): self.replies = []
        async def reply_text(self, text): self.replies.append(text)
    class Update:
        effective_user = type("User", (), {"id": 7})()
        effective_message = Message()
    for command, handler in zip(COMMANDS, handlers):
        update = Update()
        asyncio.run(handler.callback(update, type("Context", (), {"args": []})()))
        if command in {"start", "help", "pause", "resume", "kill"}:
            assert update.effective_message.replies
        else:
            assert "Analysemodus: keine Order ohne" not in update.effective_message.replies[0]
