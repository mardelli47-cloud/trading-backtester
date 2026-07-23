"""Separate, fail-closed, long-only Alpaca *paper* crypto autopilot.

It intentionally does not share the stock autopilot's market-hours or asset
validation rules.  Broker IO is injected, which also keeps tests offline.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from enum import Enum
import json, os
from pathlib import Path

PAPER_URL = "https://paper-api.alpaca.markets"

class CryptoState(str, Enum):
    DISABLED="DISABLED"; SHADOW="SHADOW"; PAPER_ACTIVE="PAPER_ACTIVE"; PAUSED="PAUSED"; RISK_LOCKED="RISK_LOCKED"; EMERGENCY_STOP="EMERGENCY_STOP"

@dataclass(frozen=True)
class CryptoAutopilotConfig:
    risk_per_trade_pct: Decimal = Decimal("0.15"); max_position_equity_pct: Decimal = Decimal("10")
    max_total_exposure_pct: Decimal = Decimal("20"); max_open_positions: int = 2; max_new_trades_per_day: int = 3
    max_daily_loss_pct: Decimal = Decimal("1"); min_reward_risk: Decimal = Decimal("2"); max_spread_pct: Decimal = Decimal("0.30")
    min_score: int = 75; min_shadow_trades: int = 30; cooldown_minutes: int = 60; max_data_age_seconds: int = 1200

@dataclass(frozen=True)
class CryptoAsset:
    symbol: str; min_order_size: Decimal; qty_increment: Decimal; price_increment: Decimal

@dataclass(frozen=True)
class CryptoMarketSnapshot:
    symbol: str; timestamp: datetime; close: Decimal; bid: Decimal; ask: Decimal; atr: Decimal
    volume: Decimal; relative_volume: Decimal; vwap: Decimal; trend_up: bool; momentum_up: bool
    breakout: bool; pullback: bool; closed: bool = True; candle_id: str = ""
    @property
    def spread_pct(self): return (self.ask-self.bid)/self.close*100 if self.close else Decimal("999")

@dataclass(frozen=True)
class CryptoTradePlan:
    symbol: str; strategy: str; entry: Decimal; stop: Decimal; target: Decimal; qty: Decimal; candle_id: str; score: int

class CryptoAutopilot:
    def __init__(self, broker=None, path: str|Path="crypto_autopilot_state.json", config=CryptoAutopilotConfig()):
        self.broker, self.path, self.config = broker, Path(path), config; self.state=CryptoState.DISABLED
        self.assets={}; self.open_trades={}; self.closed=[]; self.processed=set(); self.new_trades_today=0; self.daily_pnl=Decimal("0"); self.last_signals={}; self._pending_shadow=False; self._pending_paper=False
        self.load()
        if self.state is CryptoState.PAPER_ACTIVE: self.state=CryptoState.PAUSED; self.save()
    @staticmethod
    def normalize(symbol: str) -> str:
        value=symbol.strip().upper().replace("-", "/")
        if "/" not in value and value.endswith("USD"): value=value[:-3]+"/USD"
        if "/" not in value: value += "/USD"
        return value
    def save(self):
        self.path.write_text(json.dumps({"state":self.state.value,"closed":self.closed,"new_trades_today":self.new_trades_today,"daily_pnl":str(self.daily_pnl),"processed":list(self.processed)}, default=str), encoding="utf8")
    def load(self):
        if not self.path.exists(): return
        d=json.loads(self.path.read_text(encoding="utf8")); self.state=CryptoState(d.get("state","DISABLED")); self.closed=d.get("closed",[]); self.new_trades_today=d.get("new_trades_today",0); self.daily_pnl=Decimal(d.get("daily_pnl","0")); self.processed=set(d.get("processed",[]))
    def set_assets(self, assets):
        def get(a, key, default=""):
            return a.get(key, default) if isinstance(a, dict) else getattr(a, key, default)
        self.assets = {}
        for a in assets:
            if not (str(get(a,"asset_class")).lower()=="crypto" and str(get(a,"status")).lower()=="active" and bool(get(a,"tradable"))): continue
            symbol=self.normalize(get(a,"symbol")); minimum=Decimal(str(get(a,"min_order_size","0"))); increment=Decimal(str(get(a,"min_trade_increment",get(a,"qty_increment","0")))); price=Decimal(str(get(a,"price_increment","0")))
            if symbol.endswith("/USD") and minimum>0 and increment>0 and price>0: self.assets[symbol]=CryptoAsset(symbol,minimum,increment,price)
    def start(self):
        if not self._pending_shadow: self._pending_shadow=True; return "Erste Bestätigung gespeichert. Wiederhole /cryptoauto start."
        self._pending_shadow=False; self.state=CryptoState.SHADOW; self.save(); return "Krypto-Shadow gestartet: keine Brokerorders."
    def activate_paper(self):
        if os.getenv("ALPACA_PAPER","true").lower() != "true": raise ValueError("ALPACA_PAPER=false blockiert Krypto-Paper-Trading.")
        if len(self.closed)<self.config.min_shadow_trades: raise ValueError("Zu wenige abgeschlossene Shadow-Trades.")
        if self.state in {CryptoState.RISK_LOCKED,CryptoState.EMERGENCY_STOP}: raise ValueError("Risk Lock/Kill Switch aktiv.")
        if not self._pending_paper: self._pending_paper=True; return "Erste Paper-Bestätigung gespeichert. Wiederhole /cryptoauto paper."
        self._pending_paper=False; self.state=CryptoState.PAPER_ACTIVE; self.save(); return "Krypto-Paper-Modus aktiviert (Alpaca Paper only)."
    def score(self,s):
        # Transparent components; absent/false data never earns points.
        return min(100,(20 if s.trend_up else 0)+(15 if s.momentum_up else 0)+(15 if s.breakout or s.pullback else 0)+(15 if s.relative_volume>=1 else 0)+(15 if s.breakout or s.pullback else 0)+(15 if s.atr>0 else 0)+(5 if s.spread_pct<=self.config.max_spread_pct else 0))
    def position_size(self, entry, stop, asset, equity, buying_power, exposure=Decimal("0")):
        if entry<=stop: return Decimal("0")
        raw=equity*self.config.risk_per_trade_pct/100/(entry-stop); cap=min(buying_power/entry,equity*self.config.max_position_equity_pct/100/entry,(equity*self.config.max_total_exposure_pct/100-exposure)/entry)
        qty=min(raw,cap); inc=asset.qty_increment
        qty=(qty/inc).to_integral_value(rounding=ROUND_DOWN)*inc if inc>0 else Decimal("0")
        return qty if qty>=asset.min_order_size else Decimal("0")
    def plan(self,s, equity=Decimal("0"), buying_power=Decimal("0"), exposure=Decimal("0")):
        asset=self.assets.get(self.normalize(s.symbol)); now=datetime.now(timezone.utc)
        if not asset: self.last_signals[s.symbol]="nicht unterstütztes Alpaca-USD-Paar"; return None
        if not s.closed or now-s.timestamp>timedelta(seconds=self.config.max_data_age_seconds) or s.spread_pct>self.config.max_spread_pct: self.last_signals[s.symbol]="Daten/Spreadfilter"; return None
        if not (s.trend_up and s.momentum_up and (s.breakout or s.pullback)): self.last_signals[s.symbol]="kein bestätigtes Long-Setup"; return None
        stop=s.close-s.atr; target=s.close+(s.close-stop)*self.config.min_reward_risk; score=self.score(s); qty=self.position_size(s.ask,stop,asset,equity,buying_power,exposure)
        if score<self.config.min_score or qty<=0: self.last_signals[s.symbol]="Score/Risiko unzureichend"; return None
        return CryptoTradePlan(s.symbol,"confirmed_breakout" if s.breakout else "trend_pullback",s.ask,stop,target,qty,s.candle_id or f"{s.symbol}:{s.timestamp.isoformat()}",score)
    def open_shadow(self,p):
        if p.candle_id in self.processed or p.symbol in self.open_trades: return False
        self.processed.add(p.candle_id); self.open_trades[p.symbol]=p; self.new_trades_today+=1; self.save(); return True
    def close_shadow(self,symbol, price, reason, now=None):
        p=self.open_trades.pop(symbol,None)
        if not p: return False
        pnl=(price-p.entry)*p.qty; self.daily_pnl+=pnl; self.closed.append({"symbol":symbol,"exit":str(price),"reason":reason,"pnl":str(pnl),"r_multiple":str((price-p.entry)/(p.entry-p.stop)),"closed_at":(now or datetime.now(timezone.utc)).isoformat()}); self.save(); return True
    def status(self): return f"₿ Krypto-Pilot: {self.state.value}\nKryptohandel: 24/7; Ausführung weiterhin abhängig von Alpaca-Verfügbarkeit und Risikofiltern.\nShadow: offen {len(self.open_trades)}, abgeschlossen {len(self.closed)}/{self.config.min_shadow_trades}; Tagestrades: {self.new_trades_today}/{self.config.max_new_trades_per_day}; Tages-P&L: {self.daily_pnl}"
