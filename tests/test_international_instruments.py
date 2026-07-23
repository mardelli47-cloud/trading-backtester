from datetime import datetime, timezone
from decimal import Decimal
import pandas as pd
import pytest

from backtester.broker import MockBroker
from backtester.execution import PaperOrderService
from backtester.instruments import InstrumentResolver, ProviderRouter, YFinanceProvider
from backtester.risk import RiskManager, RiskSettings
from backtester.telegram.bot import TelegramPaperController
from backtester.telegram.ui import keyboard
from backtester.broker.base import OrderRequest


def controller():
    broker = MockBroker()
    return TelegramPaperController(PaperOrderService(broker, RiskManager(RiskSettings(), broker.account.equity), True), frozenset({1}))


def test_explicit_symbols_and_aliases_do_not_cross_replace():
    resolver = InstrumentResolver()
    assert resolver.resolve("IFX.DE").provider_symbol == "IFX.DE"
    assert resolver.resolve("IFNNY").provider_symbol == "IFNNY"
    assert resolver.resolve("EURUSD").canonical_symbol == "EUR/USD"
    assert resolver.resolve("GC=F").asset_class == "future_reference"
    assert len(resolver.search("IFX")) == 2
    assert resolver.resolve("DAX").asset_class == "index"


def test_global_symbols_are_analysis_only_and_orders_are_blocked():
    c = controller()
    assert c.validate_symbol("IFX.DE") == "IFX.DE"
    assert c.validate_symbol("EUR/USD") == "EUR/USD"
    assert c.validate_symbol("DAX") == "DAX"
    assert not any("Paper Buy" in row[0].text for row in keyboard("analysis", "IFX.DE", True).inline_keyboard)
    with pytest.raises(ValueError, match="Nur Analyse"):
        c.propose(1, OrderRequest("IFX.DE", "buy", Decimal("1")), Decimal("10"))


def test_router_preserves_alpaca_and_global_boundaries():
    stock, crypto, fallback = object(), object(), YFinanceProvider(enabled=True)
    router = ProviderRouter(stock, crypto, yfinance_provider=fallback)
    # Global resolver values cannot be sent to Alpaca stock data.
    assert router.provider_for(InstrumentResolver().resolve("IFX.DE")) is fallback
    assert router.health()["global_market_data"] == "disabled"
