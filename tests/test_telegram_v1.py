from decimal import Decimal

from backtester.broker import MockBroker
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings
from backtester.telegram.bot import TelegramPaperController
from backtester.telegram.storage import UserStore
from backtester.telegram.ui import MAIN_MENU, keyboard


def make_controller(tmp_path):
    broker = MockBroker()
    return TelegramPaperController(PaperOrderService(broker, RiskManager(RiskSettings(), broker.account.equity), True), frozenset({1}), store=UserStore(sqlite_path=str(tmp_path / "state.db")))


def test_main_menu_has_all_persistent_rows():
    assert MAIN_MENU[0] == ("📊 Analyse", "🔎 Scanner")
    assert MAIN_MENU[-1] == ("🔄 Aktualisieren", "❓ Hilfe")
    assert len(MAIN_MENU) == 7


def test_inline_keyboards_use_short_callback_data():
    for kind in ("analysis", "watchlist", "autopilot", "account", "scanner"):
        for row in keyboard(kind, "AAPL").inline_keyboard:
            assert len(row[0].callback_data) <= 64


def test_symbol_recognition_rejects_sentences_and_normalizes(tmp_path):
    controller = make_controller(tmp_path)
    assert controller.validate_symbol("aapl") == "AAPL"
    assert controller.validate_symbol("buy aapl now") is None
    assert controller.validate_symbol("TOO-LONG-SYM") is None


def test_dialog_expires_and_watchlist_is_persistent(tmp_path):
    controller = make_controller(tmp_path)
    controller.begin_dialog(1, "watchlist_add")
    assert controller.consume_dialog(1, "aapl") == ("watchlist_add", "AAPL")
    controller.add_watchlist(1, "AAPL")
    assert controller.user_watchlist(1) == ("AAPL",)
    restored = make_controller(tmp_path)
    assert restored.user_watchlist(1) == ("AAPL",)


def test_analysis_and_morning_do_not_invent_market_data(tmp_path):
    controller = make_controller(tmp_path)
    assert "nicht verfügbar" in controller.analysis_message("AAPL")
    assert "Nachrichten erfunden" in controller.command_message("morning", user_id=1)
