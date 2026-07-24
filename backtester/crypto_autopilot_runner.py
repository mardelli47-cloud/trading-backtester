from __future__ import annotations
import asyncio, os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from backtester.crypto_autopilot import CryptoAutopilot, CryptoState, CryptoMarketSnapshot

class CryptoAutopilotRunner:
    def __init__(self, autopilot: CryptoAutopilot, crypto_data, *, interval_seconds=None, symbols=None):
        self.autopilot,self.crypto_data=autopilot,crypto_data; self.interval_seconds=max(60,int(interval_seconds or os.getenv("CRYPTO_AUTOPILOT_SCAN_INTERVAL_SECONDS","300")))
        raw=symbols or os.getenv("CRYPTO_AUTOPILOT_SYMBOLS","BTC/USD,ETH/USD,SOL/USD"); self.symbols=tuple(dict.fromkeys(autopilot.normalize(x) for x in raw.split(",") if x.strip()))[:int(os.getenv("CRYPTO_AUTOPILOT_MAX_SYMBOLS","10"))]; self.running=False; self.task=None; self.last_scan=None; self.last_report=self._report(); self.last_error=""
    def _report(self): return {"checked":[],"accepted":[],"rejected":{},"data_error":{},"duplicate":{},"already_open":{},"outcomes":{},"state_blocked":False,"state":self.autopilot.state.value,"message":""}
    async def start(self):
        if not self.running: self.running=True; self.task=asyncio.create_task(self._loop())
    async def stop(self):
        self.running=False
        if self.task: self.task.cancel();
    async def _loop(self):
        while self.running:
            self.run_cycle(); await asyncio.sleep(self.interval_seconds)
    def build_snapshot(self,symbol): return self.crypto_data.snapshot(symbol) # Crypto client only; no stock clock.
    def run_cycle(self):
        self.monitor_shadow_trades(); r=self._report()
        if self.autopilot.state not in {CryptoState.SHADOW,CryptoState.PAPER_ACTIVE}:
            r.update(state_blocked=True,message="Krypto-Pilot ist nicht gestartet.",outcomes={symbol:"state_blocked" for symbol in self.symbols},checked=list(self.symbols)); self.last_report=r; return r
        for symbol in self.symbols:
            try:
                s=self.build_snapshot(symbol); r["checked"].append(symbol); p=self.autopilot.plan(s, *self.crypto_data.account_limits())
                if p is None: r["rejected"][symbol]=self.autopilot.last_signals.get(symbol,"kein bestätigtes Setup"); r["outcomes"][symbol]="rejected"; continue
                if symbol in self.autopilot.open_trades: r["already_open"][symbol]="bereits offene Position"; r["outcomes"][symbol]="already_open"; continue
                if p.candle_id in self.autopilot.processed: r["duplicate"][symbol]="bereits verarbeitete Kerze"; r["outcomes"][symbol]="duplicate"; continue
                if self.autopilot.state is CryptoState.SHADOW: self.autopilot.open_shadow(p)
                else: self.autopilot.execute_paper(p)
                r["accepted"].append(symbol); r["outcomes"][symbol]="accepted"
            except Exception as e: r["data_error"][symbol]=str(e); r["outcomes"][symbol]="data_error"
        self.last_scan=datetime.now(timezone.utc); self.last_report=r; return r
    def monitor_shadow_trades(self):
        for symbol,p in list(self.autopilot.open_trades.items()):
            try:
                bar=self.crypto_data.latest_closed_bar(symbol); low,high=Decimal(str(bar.low)),Decimal(str(bar.high))
                if low<=p.stop: self.autopilot.close_shadow(symbol,p.stop,"stop")
                elif high>=p.target: self.autopilot.close_shadow(symbol,p.target,"target")
            except Exception as e: self.last_error=f"{symbol}: {type(e).__name__}"
    def status(self): return f"Runner läuft: {'ja' if self.running else 'nein'}\nScanintervall: {self.interval_seconds}s\nKonfigurierte Paare: {', '.join(self.symbols)}\nLetzter Scan: {self.last_scan or '–'}\n" + ("⚠️ Kein persistenter DATABASE_URL-Store konfiguriert; Render-Neustarts können Zustände verlieren." if not os.getenv("DATABASE_URL") else "Persistenter DATABASE_URL-Store aktiv.")
