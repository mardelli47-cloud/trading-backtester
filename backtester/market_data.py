"""Central, read-only Alpaca market-data access.

This module deliberately uses Alpaca's data client, never the paper trading
endpoint, for prices and bars.  TradingClient is only used for the market clock.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

LOG = logging.getLogger(__name__)


class MarketDataError(RuntimeError):
    """A safe, user-facing classification of a market-data failure."""


def _error_message(exc: Exception) -> str:
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    text = str(exc).lower()
    if status in (401, 403) or "unauthorized" in text or "forbidden" in text:
        return "Market-Data-Berechtigung fehlt oder die API-Schlüssel sind ungültig. Prüfe den IEX-Feed."
    if status == 429 or "rate limit" in text:
        return "Market-Data Rate Limit erreicht. Bitte später erneut versuchen."
    if "timeout" in text:
        return "Market-Data-Anfrage hat ein Timeout erreicht."
    if "not found" in text or status == 404:
        return "Symbol ungültig oder bei Alpaca nicht verfügbar."
    return "Externer Market-Data-Dienst ist derzeit nicht erreichbar."


class MarketDataService:
    """One reusable Alpaca market-data service with an IEX default feed."""

    def __init__(self, api_key: str | None = None, secret_key: str | None = None,
                 feed: str | None = None, data_client: Any = None, trading_client: Any = None):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.feed = (feed or os.getenv("ALPACA_DATA_FEED", "iex")).lower()
        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca API-Schlüssel fehlen. Setze ALPACA_API_KEY und ALPACA_SECRET_KEY.")
        if self.feed not in {"iex", "sip", "otc"}:
            raise ValueError("ALPACA_DATA_FEED muss iex, sip oder otc sein.")
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise RuntimeError("alpaca-py ist nicht installiert.") from exc
        # StockHistoricalDataClient targets Alpaca's market-data API, separately
        # from the Paper TradingClient used by order/account code.
        self.client = data_client or StockHistoricalDataClient(self.api_key, self.secret_key)
        self.trading_client = trading_client or TradingClient(self.api_key, self.secret_key, paper=True)

    def _feed(self):
        from alpaca.data.enums import DataFeed
        return DataFeed(self.feed)

    def _call(self, symbol: str, operation: str, fn):
        try:
            return fn()
        except Exception as exc:
            LOG.warning("market_data_error provider=alpaca symbol=%s operation=%s status=%s type=%s", symbol, operation, getattr(exc, "status_code", None), type(exc).__name__)
            raise MarketDataError(_error_message(exc)) from exc

    def get_latest_price(self, symbol: str) -> float:
        from alpaca.data.requests import StockLatestTradeRequest
        trade = self._call(symbol, "latest_trade", lambda: self.client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol, feed=self._feed()))[symbol])
        return float(trade.price)

    def get_latest_quote(self, symbol: str):
        from alpaca.data.requests import StockLatestQuoteRequest
        return self._call(symbol, "latest_quote", lambda: self.client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=self._feed()))[symbol])

    def get_bars(self, symbol: str, timeframe, start=None, end=None, limit: int | None = None) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest
        request = StockBarsRequest(symbol_or_symbols=symbol, timeframe=timeframe, start=start, end=end, limit=limit, feed=self._feed())
        bars = self._call(symbol, "bars", lambda: self.client.get_stock_bars(request))
        frame = bars.df if hasattr(bars, "df") else pd.DataFrame(bars)
        if frame.empty:
            raise MarketDataError("Keine historischen Bars für dieses Symbol verfügbar.")
        if isinstance(frame.index, pd.MultiIndex):
            frame = frame.reset_index(level=0, drop=True)
        return frame.sort_index()

    def _closed(self, bars: pd.DataFrame, minutes: int | None = None) -> pd.DataFrame:
        result = bars.copy()
        now = datetime.now(timezone.utc)
        index = pd.to_datetime(result.index, utc=True)
        if minutes is None:  # Daily bar is only confirmed after its UTC calendar day.
            result = result[index.date < now.date()]
        else:
            result = result[index + pd.Timedelta(minutes=minutes) <= now]
        if result.empty:
            raise MarketDataError("Keine abgeschlossenen Bars verfügbar.")
        return result

    def get_daily_bars(self, symbol: str, limit: int = 101) -> pd.DataFrame:
        from alpaca.data.timeframe import TimeFrame
        return self._closed(self.get_bars(symbol, TimeFrame.Day, start=datetime.now(timezone.utc) - timedelta(days=limit * 3), limit=limit))

    def get_intraday_bars(self, symbol: str, timeframe="15Min", limit: int = 101) -> pd.DataFrame:
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        minutes = 15 if str(timeframe).lower().startswith("15") else 30
        tf = TimeFrame(minutes, TimeFrameUnit.Minute)
        return self._closed(self.get_bars(symbol, tf, start=datetime.now(timezone.utc) - timedelta(days=14), limit=limit), minutes)

    def validate_symbol(self, symbol: str) -> bool:
        try:
            self.get_latest_price(symbol)
            return True
        except MarketDataError:
            return False

    def get_market_clock(self):
        return self._call("market", "clock", self.trading_client.get_clock)

    def healthcheck(self) -> str:
        try:
            self.get_market_clock()
            return "ok"
        except Exception:
            return "error"
