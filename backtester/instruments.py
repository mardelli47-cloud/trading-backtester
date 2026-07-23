"""Provider-neutral, analysis-only international market data.

No class in this module submits orders.  Symbols are resolved to an immutable
``instrument_id`` so a German listing, ADR, index, or ETF cannot be swapped.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os, time
from typing import Any, Protocol
import pandas as pd

ANALYSIS_CLASSES = {"global_equity", "adr", "otc_equity", "forex", "index", "commodity", "future_reference"}

@dataclass(frozen=True)
class Instrument:
    instrument_id: str; canonical_symbol: str; provider_symbol: str; display_symbol: str
    name: str; asset_class: str; asset_subtype: str = ""; exchange: str = ""
    mic: str = ""; country: str = ""; currency: str = "USD"; timezone: str = "UTC"
    data_provider: str = ""; trading_provider: str = ""; tradable: bool = False
    paper_tradable: bool = False; analysis_only: bool = True; shortable: bool = False
    fractionable: bool = False; market_schedule_type: str = ""; metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class MarketDataResult:
    instrument_id: str; provider: str; timestamp: datetime; timezone: str; currency: str; exchange: str
    delayed: bool = True; estimated_delay_seconds: int | None = None; stale: bool = False; staleness_seconds: float = 0
    completeness: float = 0; warnings: list[str] = field(default_factory=list); is_realtime: bool = False
    is_analysis_only: bool = True; price: float | None = None; quote: dict[str, float] | None = None; bars: pd.DataFrame | None = None

class MarketDataProvider(Protocol):
    def search_instruments(self, query: str) -> list[Instrument]: ...
    def resolve_instrument(self, query: str) -> Instrument | None: ...
    def validate_instrument(self, instrument: Instrument) -> bool: ...
    def get_latest_price(self, instrument: Instrument) -> MarketDataResult: ...
    def get_latest_quote(self, instrument: Instrument) -> MarketDataResult: ...
    def get_snapshot(self, instrument: Instrument) -> MarketDataResult: ...
    def get_bars(self, instrument: Instrument, timeframe: str, start=None, end=None, limit: int = 100) -> MarketDataResult: ...
    def get_daily_bars(self, instrument: Instrument, limit: int = 100) -> MarketDataResult: ...
    def get_intraday_bars(self, instrument: Instrument, timeframe: str = "15min", limit: int = 100) -> MarketDataResult: ...
    def get_previous_day_levels(self, instrument: Instrument) -> MarketDataResult: ...
    def get_market_status(self, instrument: Instrument) -> str: ...

# Purposefully small: aliases are discovery aids, not a substitute for provider search.
def _inst(symbol, name, cls, exchange, currency="EUR", timezone_name="Europe/Berlin", subtype="", provider_symbol=None):
    provider_symbol = provider_symbol or symbol
    return Instrument(f"{cls}:{provider_symbol}", symbol, provider_symbol, symbol, name, cls, subtype, exchange,
        country="DE" if exchange == "Xetra" else "", currency=currency, timezone=timezone_name,
        market_schedule_type="forex" if cls == "forex" else ("index" if cls == "index" else "reference" if cls in {"commodity", "future_reference"} else "exchange"))

CATALOG = {
 "IFX.DE": _inst("IFX.DE", "Infineon AG", "global_equity", "Xetra"), "IFNNY": _inst("IFNNY", "Infineon Technologies ADR", "otc_equity", "OTC", "USD", "America/New_York"),
 "SAP.DE": _inst("SAP.DE", "SAP SE", "global_equity", "Xetra"), "SIE.DE": _inst("SIE.DE", "Siemens AG", "global_equity", "Xetra"), "ALV.DE": _inst("ALV.DE", "Allianz SE", "global_equity", "Xetra"),
 "^GDAXI": _inst("DAX", "DAX Performance Index", "index", "Germany", "EUR", "Europe/Berlin", provider_symbol="^GDAXI"), "^STOXX50E": _inst("EUROSTOXX50", "EURO STOXX 50", "index", "Europe", "EUR", "Europe/Berlin", provider_symbol="^STOXX50E"),
 "^FTSE": _inst("FTSE100", "FTSE 100", "index", "London", "GBP", "Europe/London", provider_symbol="^FTSE"), "^FCHI": _inst("CAC40", "CAC 40", "index", "Paris", "EUR", "Europe/Paris", provider_symbol="^FCHI"),
 "EURUSD=X": _inst("EUR/USD", "Euro / US Dollar", "forex", "Forex", "USD", "UTC", provider_symbol="EURUSD=X"), "GBPUSD=X": _inst("GBP/USD", "British Pound / US Dollar", "forex", "Forex", "USD", "UTC", provider_symbol="GBPUSD=X"), "JPY=X": _inst("USD/JPY", "US Dollar / Japanese Yen", "forex", "Forex", "JPY", "UTC", provider_symbol="JPY=X"),
 "GC=F": _inst("GC=F", "Gold Future Reference", "future_reference", "COMEX reference", "USD", "America/New_York", "future_reference"), "SI=F": _inst("SI=F", "Silver Future Reference", "future_reference", "COMEX reference", "USD", "America/New_York", "future_reference"), "CL=F": _inst("CL=F", "WTI Crude Future Reference", "future_reference", "NYMEX reference", "USD", "America/New_York", "future_reference"), "BZ=F": _inst("BZ=F", "Brent Crude Future Reference", "future_reference", "ICE reference", "USD", "Europe/London", "future_reference"),
}
ALIASES = {"INFINEON": ["IFX.DE", "IFNNY"], "IFX": ["IFX.DE", "IFNNY"], "DAX": ["^GDAXI"], "DAX INDEX": ["^GDAXI"], "EURO STOXX 50": ["^STOXX50E"], "EURO DOLLAR": ["EURUSD=X"], "EURUSD": ["EURUSD=X"], "EUR/USD": ["EURUSD=X"], "GBP/USD": ["GBPUSD=X"], "USD/JPY": ["JPY=X"], "GOLD": ["GC=F"], "GOLD FUTURE": ["GC=F"], "SILBER": ["SI=F"], "SILVER": ["SI=F"], "BRENT": ["BZ=F"], "WTI": ["CL=F"], "SIEMENS": ["SIE.DE"], "SAP": ["SAP.DE"], "ALLIANZ": ["ALV.DE"]}

class InstrumentResolver:
    def __init__(self, providers: list[MarketDataProvider] | None = None): self.providers = providers or []
    def search(self, query: str) -> list[Instrument]:
        q = query.strip().upper(); keys = ALIASES.get(q, [q])
        found = [CATALOG[k] for k in keys if k in CATALOG]
        if found: return found
        for provider in self.providers:
            try:
                found.extend(provider.search_instruments(query))
            except Exception: continue
        return list({x.instrument_id: x for x in found}.values())
    def resolve(self, query: str) -> Instrument | None:
        found = self.search(query)
        return found[0] if len(found) == 1 else None

class YFinanceProvider:
    """Bounded, cached analysis fallback; Yahoo data is never claimed realtime."""
    name = "yfinance"
    def __init__(self, enabled: bool | None = None, ttl: int | None = None):
        self.enabled = (os.getenv("ENABLE_YFINANCE_FALLBACK", "false").lower() == "true") if enabled is None else enabled
        self.ttl = ttl or int(os.getenv("MARKET_DATA_CACHE_TTL_SECONDS", "60")); self._cache: dict[tuple, tuple[float, MarketDataResult]] = {}
    def search_instruments(self, query): return InstrumentResolver().search(query)
    def resolve_instrument(self, query): return InstrumentResolver().resolve(query)
    def validate_instrument(self, instrument): return self.enabled
    def _result(self, instrument, bars=None, price=None):
        return MarketDataResult(instrument.instrument_id, self.name, datetime.now(timezone.utc), instrument.timezone, instrument.currency, instrument.exchange, True, 900, warnings=["yfinance fallback: delayed/availability not guaranteed"], is_analysis_only=True, price=price, bars=bars, completeness=1 if bars is not None else 0)
    def get_bars(self, instrument, timeframe, start=None, end=None, limit=100):
        if not self.enabled: raise RuntimeError("yfinance-Fallback ist deaktiviert.")
        key=(instrument.instrument_id,timeframe,limit); cached=self._cache.get(key)
        if cached and time.monotonic()-cached[0] < self.ttl: return cached[1]
        import yfinance as yf
        period="2y" if timeframe == "1d" else "60d"; interval="1d" if timeframe == "1d" else timeframe
        frame=yf.Ticker(instrument.provider_symbol).history(period=period, interval=interval, timeout=float(os.getenv("PROVIDER_REQUEST_TIMEOUT_SECONDS", "10")))
        if frame.empty: raise RuntimeError("Keine historischen Daten verfügbar.")
        frame.columns=[str(c).lower() for c in frame.columns]; frame=frame.rename(columns={"stock splits":"stock_splits"}).tail(limit)
        result=self._result(instrument, frame); self._cache[key]=(time.monotonic(),result); return result
    def get_daily_bars(self, instrument, limit=100): return self.get_bars(instrument,"1d",limit=limit)
    def get_intraday_bars(self, instrument,timeframe="15m",limit=100): return self.get_bars(instrument,timeframe,limit=limit)
    def get_latest_price(self, instrument):
        result=self.get_daily_bars(instrument,2); result.price=float(result.bars["close"].iloc[-1]); return result
    get_latest_quote=get_latest_price; get_snapshot=get_latest_price
    def get_previous_day_levels(self, instrument): return self.get_daily_bars(instrument,2)
    def get_market_status(self, instrument): return "analysis_only"

class ProviderRouter:
    def __init__(self, alpaca_stock=None, alpaca_crypto=None, global_provider=None, yfinance_provider=None): self.alpaca_stock,self.alpaca_crypto,self.global_provider,self.yfinance_provider=alpaca_stock,alpaca_crypto,global_provider,yfinance_provider
    def provider_for(self, instrument: Instrument):
        if instrument.asset_class in {"us_equity", "etf"}: return self.alpaca_stock
        if instrument.asset_class == "crypto": return self.alpaca_crypto
        if self.global_provider and getattr(self.global_provider, "enabled", True): return self.global_provider
        return self.yfinance_provider if self.yfinance_provider and self.yfinance_provider.enabled else None
    def health(self): return {"global_market_data": "ok" if self.global_provider and getattr(self.global_provider, "enabled", True) else "disabled", "yfinance_fallback": "ok" if self.yfinance_provider and self.yfinance_provider.enabled else "disabled"}

class TwelveDataProvider:
    """Official Twelve Data HTTP API adapter, enabled only with its API key.

    The API supports symbol search, global equities, FX and indices; unsupported
    symbols fail explicitly rather than being remapped.
    """
    name = "twelve_data"
    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY", "")
        self.timeout = timeout or float(os.getenv("PROVIDER_REQUEST_TIMEOUT_SECONDS", "10"))
    @property
    def enabled(self): return bool(self.api_key)
    def _request(self, path, **params):
        if not self.enabled: raise RuntimeError("Globaler Marktdatenprovider ist nicht konfiguriert (TWELVE_DATA_API_KEY fehlt).")
        import json, urllib.parse, urllib.request
        params["apikey"] = self.api_key
        url="https://api.twelvedata.com/"+path+"?"+urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response: payload=json.load(response)
        except TimeoutError as exc: raise RuntimeError("Marktdaten-Timeout.") from exc
        if payload.get("status") == "error":
            raise RuntimeError("Globaler Marktdatenprovider: " + payload.get("message", "unbekannter Fehler"))
        return payload
    def search_instruments(self, query):
        payload=self._request("symbol_search", symbol=query); result=[]
        for item in payload.get("data", []):
            symbol=item.get("symbol", ""); typ=item.get("instrument_type", "").lower(); cls="forex" if typ == "forex" else "index" if typ == "index" else "global_equity"
            result.append(Instrument(f"{cls}:{symbol}:{item.get('exchange','')}", symbol, symbol, symbol, item.get("instrument_name", symbol), cls, exchange=item.get("exchange", ""), currency=item.get("currency", "USD"), timezone=item.get("timezone", "UTC"), data_provider=self.name, analysis_only=True))
        return result
    def resolve_instrument(self, query):
        found=self.search_instruments(query); return found[0] if len(found)==1 else None
    def validate_instrument(self, instrument): return self.enabled
    def get_bars(self, instrument, timeframe, start=None, end=None, limit=100):
        payload=self._request("time_series", symbol=instrument.provider_symbol, interval=timeframe, outputsize=limit)
        values=payload.get("values", []);
        if not values: raise RuntimeError("Keine historischen Daten verfügbar.")
        frame=pd.DataFrame(values); frame["datetime"]=pd.to_datetime(frame["datetime"]); frame=frame.set_index("datetime").sort_index()
        for column in frame.columns: frame[column]=pd.to_numeric(frame[column], errors="ignore")
        return MarketDataResult(instrument.instrument_id,self.name,datetime.now(timezone.utc),instrument.timezone,instrument.currency,instrument.exchange,False,0,completeness=1,is_realtime=True,is_analysis_only=True,bars=frame)
    def get_daily_bars(self,instrument,limit=100): return self.get_bars(instrument,"1day",limit=limit)
    def get_intraday_bars(self,instrument,timeframe="15min",limit=100): return self.get_bars(instrument,timeframe,limit=limit)
    def get_latest_price(self,instrument):
        payload=self._request("price",symbol=instrument.provider_symbol); price=float(payload["price"])
        return MarketDataResult(instrument.instrument_id,self.name,datetime.now(timezone.utc),instrument.timezone,instrument.currency,instrument.exchange,False,0,completeness=1,is_realtime=True,is_analysis_only=True,price=price)
    get_latest_quote=get_latest_price; get_snapshot=get_latest_price
    def get_previous_day_levels(self,instrument): return self.get_daily_bars(instrument,2)
    def get_market_status(self,instrument): return "analysis_only"
