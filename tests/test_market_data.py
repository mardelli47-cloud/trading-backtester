from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from backtester.market_data import MarketDataError, MarketDataService
from backtester.telegram.bot import TelegramPaperController, is_user_allowed
from backtester.telegram.config import TelegramSettings
from backtester.broker import MockBroker
from backtester.execution import PaperOrderService
from backtester.risk import RiskManager, RiskSettings


class DataClient:
    def __init__(self, frame): self.frame, self.requests = frame, []
    def get_stock_bars(self, request): self.requests.append(request); return SimpleNamespace(df=self.frame)
    def get_stock_latest_trade(self, request): return {"AAPL": SimpleNamespace(price=123.45)}
    def get_stock_latest_quote(self, request): return {"AAPL": SimpleNamespace(bid_price=123, ask_price=124)}


def bars(rows=101):
    index = pd.date_range(datetime.now(timezone.utc) - timedelta(days=rows + 2), periods=rows, freq="D")
    return pd.DataFrame({"open": range(rows), "high": range(2, rows + 2), "low": range(rows), "close": range(1, rows + 1), "volume": [100] * rows}, index=index)


def test_market_data_uses_iex_and_returns_closed_daily_bars():
    client = DataClient(bars())
    data = MarketDataService("key", "secret", "iex", client, SimpleNamespace(get_clock=lambda: None))
    result = data.get_daily_bars("AAPL", 100)
    assert len(result) >= 100
    assert str(client.requests[0].feed).lower().endswith("iex")


def test_empty_bars_and_rate_limit_are_safe_errors():
    with pytest.raises(MarketDataError, match="Keine historischen"):
        MarketDataService("key", "secret", data_client=DataClient(pd.DataFrame()), trading_client=SimpleNamespace(get_clock=lambda: None)).get_daily_bars("AAPL")
    class Limited(DataClient):
        def get_stock_latest_trade(self, request):
            error = RuntimeError("rate limit"); error.status_code = 429; raise error
    with pytest.raises(MarketDataError, match="Rate Limit"):
        MarketDataService("key", "secret", data_client=Limited(bars()), trading_client=SimpleNamespace(get_clock=lambda: None)).get_latest_price("AAPL")


def test_analysis_keeps_daily_result_when_intraday_is_unavailable():
    class DailyOnly:
        def get_daily_bars(self, *args): return bars()
        def get_latest_price(self, *args): return 123.45
        def get_intraday_bars(self, *args): raise MarketDataError("Timeout")
        def validate_symbol(self, *args): return True
    broker = MockBroker()
    controller = TelegramPaperController(PaperOrderService(broker, RiskManager(RiskSettings(), broker.account.equity), True), frozenset({7}), market_data=DailyOnly())
    assert "Intraday: vorübergehend nicht verfügbar" in controller.analysis_message("AAPL")


@pytest.mark.parametrize("raw, expected", [("123", {123}), ("123, 456", {123, 456}), ('"123"', {123}), ("[123,456]", {123, 456})])
def test_allowed_id_parsing(raw, expected):
    assert TelegramSettings.parse_allowed_user_ids(raw) == expected


def test_invalid_id_and_user_not_chat_authorization():
    with pytest.raises(ValueError): TelegramSettings.parse_allowed_user_ids("123,nope")
    update = SimpleNamespace(effective_user=SimpleNamespace(id=7), effective_chat=SimpleNamespace(id=999))
    assert is_user_allowed(update, frozenset({7}))
    assert not is_user_allowed(update, frozenset({999}))
