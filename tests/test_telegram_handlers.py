import asyncio
import logging
from types import SimpleNamespace

import pytest

from backtester.broker import MockBroker
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings
from backtester.telegram.bot import _BUTTON_COMMANDS, TelegramPaperController, build_application
from backtester.telegram.logging import SensitiveDataFilter


def make_controller():
    broker = MockBroker()
    service = PaperOrderService(broker, RiskManager(RiskSettings(), broker.account.equity), True)
    return TelegramPaperController(service, frozenset({7}))


class Message:
    def __init__(self, text=""):
        self.text, self.replies = text, []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


class Query:
    def __init__(self, data):
        self.data, self.answers, self.edits = data, 0, []
        self.from_user = SimpleNamespace(id=7)
        self.message = Message()

    async def answer(self):
        self.answers += 1

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(text)


def message_handler(app):
    return next(handler for handler in app.handlers[0] if handler.__class__.__name__ == "MessageHandler")


def command_handler(app, command):
    return next(handler for handler in app.handlers[0] if command in getattr(handler, "commands", set()))


@pytest.mark.parametrize(("button", "expected"), [
    ("📊 Analyse", "Welches Symbol möchtest du analysieren?"),
    ("🔎 Scanner", "🔎 Scanner"),
    ("⭐ Watchlist", "Watchlist:"),
    ("🌅 Morning", "🌅 Morning Briefing"),
    ("💼 Konto", "Paper-Konto"),
    ("📈 Positionen", "Offene Positionen:"),
    ("🧾 Orders", "Orders:"),
    ("⚙️ Risiko", "Risikolimits"),
    ("🤖 Autopilot", "Autopilot:"),
    ("📔 Journal", "📔 Journal"),
    ("📅 Termine", "📅 Termine"),
    ("⚙️ Einstellungen", "⚙️ Einstellungen"),
    ("🔄 Aktualisieren", "Paper-Konto"),
    ("❓ Hilfe", "Trading-App"),
])
def test_reply_keyboard_button_uses_real_message_handler_without_context_args(button, expected):
    app = build_application(make_controller(), "123456:abcdefghijklmnopqrstuv")
    message = Message(button)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=7), effective_message=message, callback_query=None)
    asyncio.run(message_handler(app).callback(update, SimpleNamespace(args=None)))
    assert message.replies
    assert expected in message.replies[-1]
    assert not any("⚠️ Die Funktion konnte nicht ausgeführt werden." in reply for reply in message.replies)


def test_slash_handlers_support_empty_and_populated_arguments():
    app = build_application(make_controller(), "123456:abcdefghijklmnopqrstuv")
    for args, expected in (([], "Watchlist:"), (["aapl,msft"], "AAPL, MSFT")):
        message = Message()
        update = SimpleNamespace(effective_user=SimpleNamespace(id=7), effective_message=message, callback_query=None)
        asyncio.run(command_handler(app, "watchlist").callback(update, SimpleNamespace(args=args)))
        assert expected in message.replies[-1]


def test_callback_is_answered_once():
    app = build_application(make_controller(), "123456:abcdefghijklmnopqrstuv")
    callback = next(handler for group in app.handlers.values() for handler in group if handler.__class__.__name__ == "CallbackQueryHandler")
    query = Query("menu")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=7), effective_message=query.message, callback_query=query)
    asyncio.run(callback.callback(update, SimpleNamespace(args=None)))
    assert query.answers == 1


def test_handler_error_is_logged_with_traceback_and_safe_error(caplog):
    controller = make_controller()
    controller.service.broker.get_account = lambda: (_ for _ in ()).throw(RuntimeError("secret failure"))
    app = build_application(controller, "123456:abcdefghijklmnopqrstuv")
    message = Message()
    update = SimpleNamespace(effective_user=SimpleNamespace(id=7), effective_message=message, callback_query=None)
    with caplog.at_level(logging.ERROR):
        asyncio.run(command_handler(app, "account").callback(update, SimpleNamespace(args=[])))
    assert "telegram_handler_failed action=account update_type=message error_id=" in caplog.text
    assert any(record.exc_info for record in caplog.records)
    assert "secret failure" not in message.replies[-1]
    assert message.replies[-1].startswith("⚠️ Die Funktion konnte nicht ausgeführt werden. Fehler-ID: ")


def test_sensitive_filter_masks_tokens_and_http_client_info_logs(caplog):
    logger = logging.getLogger("httpx")
    original_level = logger.level
    try:
        logger.setLevel(logging.WARNING)
        with caplog.at_level(logging.INFO):
            logger.info("https://api.telegram.org/bot123456:abcdefghijklmnopqrstuv/sendMessage")
        assert not caplog.records
    finally:
        logger.setLevel(original_level)
    record = logging.LogRecord("test", logging.INFO, __file__, 1,
                               "Authorization: Bearer xyz; ALPACA_API_KEY=key; https://api.telegram.org/bot123456:abcdefghijklmnopqrstuv/sendMessage", (), None)
    SensitiveDataFilter().filter(record)
    assert "abcdefghijklmnopqrstuv" not in record.msg
    assert "key" not in record.msg
    assert "bot***REDACTED***/sendMessage" in record.msg


def test_callback_error_is_logged_and_keeps_traceback_private(caplog):
    controller = make_controller()
    controller.service.broker.get_account = lambda: (_ for _ in ()).throw(RuntimeError("callback secret"))
    app = build_application(controller, "123456:abcdefghijklmnopqrstuv")
    callback = next(handler for group in app.handlers.values() for handler in group if handler.__class__.__name__ == "CallbackQueryHandler")
    query = Query("cmd:account")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=7), effective_message=query.message, callback_query=query)
    with caplog.at_level(logging.ERROR):
        asyncio.run(callback.callback(update, SimpleNamespace(args=None)))
    assert query.answers == 1
    assert "telegram_handler_failed action=cmd:account update_type=callback_query error_id=" in caplog.text
    assert any(record.exc_info for record in caplog.records)
    assert "callback secret" not in query.edits[-1]
    assert query.edits[-1].startswith("⚠️ Die Funktion konnte nicht ausgeführt werden. Fehler-ID: ")


def test_missing_global_provider_does_not_break_account_or_risk():
    controller = make_controller()
    assert "Globaler Marktdatenprovider nicht konfiguriert" in controller.analysis_message("IFX.DE")
    assert "Paper-Konto" in controller.command_message("account", user_id=7)
    assert "Risikolimits" in controller.command_message("risk", user_id=7)
