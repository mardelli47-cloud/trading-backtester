"""Scheduled, fail-closed Alpaca-paper autopilot runner.

The runner deliberately has no trading-client construction; it receives the
existing paper-only order service and read-only Alpaca market-data service.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from backtester.autopilot import Autopilot, AutopilotState, MarketSnapshot, TradePlan
from backtester.market_data import MarketDataError, MarketDataService

LOG = logging.getLogger(__name__)

class AutopilotRunner:
    def __init__(self, autopilot: Autopilot, market_data: MarketDataService, *, interval_seconds: int | None = None, symbols: str | None = None, max_symbols: int | None = None, plan_max_age_minutes: int | None = None):
        self.autopilot, self.market_data = autopilot, market_data
        self.interval_seconds = max(60, int(interval_seconds or os.getenv("AUTOPILOT_SCAN_INTERVAL_SECONDS", "300")))
        raw = symbols if symbols is not None else os.getenv("AUTOPILOT_SYMBOLS", "AAPL,MSFT,NVDA,AMZN,META,SPY,QQQ")
        self.max_symbols = max(1, min(20, int(max_symbols or os.getenv("AUTOPILOT_MAX_SYMBOLS", "20"))))
        self.symbols = tuple(dict.fromkeys(x.strip().upper() for x in raw.split(",") if x.strip()))[:self.max_symbols]
        self.plan_max_age = timedelta(minutes=max(1, int(plan_max_age_minutes or os.getenv("AUTOPILOT_PLAN_MAX_AGE_MINUTES", "60"))))
        self.running = False; self.task: asyncio.Task | None = None; self.last_scan: datetime | None = None
        self.next_scan: datetime | None = None; self.last_error = ""; self.last_report = self._report()

    def _report(self) -> dict:
        return {"checked": [], "accepted": [], "rejected": {}, "data_error": {}, "duplicate": {}, "already_open": {}, "outcomes": {}, "state_blocked": False, "state": self.autopilot.state.value, "message": ""}

    async def start(self) -> None:
        if self.running: return
        self.running = True; self.task = asyncio.create_task(self._loop(), name="autopilot-runner")

    async def stop(self) -> None:
        self.running = False
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
            self.task = None

    async def _loop(self) -> None:
        while self.running:
            try: self.run_cycle()
            except Exception as exc:
                self.last_error = f"kritischer Runnerfehler: {type(exc).__name__}"
                self.autopilot.lock(self.last_error)
                LOG.exception("autopilot_runner_critical_error")
            self.next_scan = datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)
            await asyncio.sleep(self.interval_seconds)

    def build_snapshot(self, symbol: str, now: datetime | None = None) -> MarketSnapshot:
        now = now or datetime.now(timezone.utc)
        clock = self.market_data.get_market_clock()
        if not getattr(clock, "is_open", False): raise MarketDataError("US-Aktienmarkt ist geschlossen.")
        quote = self.market_data.get_latest_quote(symbol); bid, ask = Decimal(str(quote.bid_price)), Decimal(str(quote.ask_price))
        if bid <= 0 or ask <= 0: raise MarketDataError("Bid/Ask fehlen.")
        intraday, daily = self.market_data.get_intraday_bars(symbol, "15Min", 101), self.market_data.get_daily_bars(symbol, 30)
        bar = intraday.iloc[-1]; timestamp = intraday.index[-1].to_pydatetime()
        if timestamp.tzinfo is None: timestamp = timestamp.replace(tzinfo=timezone.utc)
        if now - timestamp > timedelta(seconds=self.autopilot.config.max_data_age_seconds): raise MarketDataError("Abgeschlossene 15-Minuten-Kerze ist veraltet.")
        close, high, low = Decimal(str(bar.close)), Decimal(str(bar.high)), Decimal(str(bar.low))
        atr = Decimal(str((daily["high"] - daily["low"]).tail(14).mean()))
        vwap = Decimal(str(getattr(bar, "vwap", close)))
        dclose = daily["close"]
        trend = bool(close >= Decimal(str(dclose.tail(20).mean())))
        momentum = bool(len(dclose) >= 10 and dclose.iloc[-1] >= dclose.iloc[-10])
        vol = intraday["volume"]
        relative_volume = Decimal(str(vol.iloc[-1] / vol.tail(20).mean())) if len(vol) >= 20 and vol.tail(20).mean() else Decimal("0")
        resistance, support = Decimal(str(intraday["high"].iloc[-21:-1].max())), Decimal(str(intraday["low"].iloc[-21:-1].min()))
        breakout, pullback = close > resistance and close >= vwap, low <= vwap and close >= vwap
        spy = self.market_data.get_daily_bars("SPY", 30)["close"]
        relative_strength = Decimal(str((dclose.iloc[-1] / dclose.iloc[-10]) / (spy.iloc[-1] / spy.iloc[-10]))) if len(dclose) >= 10 and len(spy) >= 10 else Decimal("0")
        return MarketSnapshot(symbol, timestamp, close, bid, ask, int(daily["volume"].iloc[-1]), atr, vwap, trend, momentum, relative_strength, relative_volume, breakout, pullback, True, "stock", "NYSE", True)

    def run_cycle(self) -> dict:
        self.monitor_open_plans()
        if self.autopilot.state not in {AutopilotState.SHADOW, AutopilotState.PAPER_ACTIVE}:
            report = self._report()
            report.update(state_blocked=True, message="Autopilot ist nicht gestartet.", checked=list(self.symbols), outcomes={symbol: "state_blocked" for symbol in self.symbols})
            self.last_report = report
            return report
        if not self.symbols: raise ValueError("AUTOPILOT_SYMBOLS ist leer; kein unkontrollierter Vollmarkt-Scan.")
        report = self._report()
        snapshots = []
        for symbol in self.symbols:
            try: snapshots.append(self.build_snapshot(symbol)); report["checked"].append(symbol)
            except Exception as exc: report["checked"].append(symbol); report["data_error"][symbol] = str(exc); report["outcomes"][symbol] = "data_error"
        already_processed = {f"{snapshot.symbol}:{snapshot.timestamp.isoformat()}" for snapshot in snapshots if f"{snapshot.symbol}:{snapshot.timestamp.isoformat()}" in self.autopilot.processed_candles}
        plans = self.autopilot.scan(snapshots)
        plans_by_symbol = {plan.symbol: plan for plan in plans}
        for snapshot in snapshots:
            symbol, plan = snapshot.symbol, plans_by_symbol.get(snapshot.symbol)
            if plan is None:
                category = "already_open" if symbol in self.autopilot.open_plans else ("duplicate" if f"{symbol}:{snapshot.timestamp.isoformat()}" in already_processed else "rejected")
                report[category][symbol] = "bereits offene Position" if category == "already_open" else ("bereits verarbeitete Kerze" if category == "duplicate" else self.autopilot.last_signals.get(symbol, "kein bestätigtes Setup"))
                report["outcomes"][symbol] = category
            else:
                self.process_plans([plan], report)
        self.last_scan = datetime.now(timezone.utc); self.next_scan = self.last_scan + timedelta(seconds=self.interval_seconds); self.last_report = report
        LOG.info("autopilot_cycle state=%s checked=%d rejected=%d plans=%d", self.autopilot.state.value, len(report["checked"]), len(report["rejected"]), len(plans))
        return report

    def process_plans(self, plans: list[TradePlan], report: dict | None = None) -> None:
        for plan in plans:
            try:
                self.autopilot.execute(plan)
                if report is not None: report["accepted"].append(plan.symbol); report["outcomes"][plan.symbol] = "accepted"
            except Exception as exc:
                target = report if report is not None else self.last_report
                target.setdefault("rejected", {})[plan.symbol] = str(exc); target.setdefault("outcomes", {})[plan.symbol] = "rejected"

    def monitor_open_plans(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        for symbol, plan in list(self.autopilot.open_plans.items()):
            if self.autopilot.state is not AutopilotState.SHADOW: continue
            try:
                bar = self.market_data.get_intraday_bars(symbol, "15Min", 2).iloc[-1]
                # Conservative: on a bar touching both thresholds, stop wins.
                if Decimal(str(bar.low)) <= plan.stop: self.autopilot.close_shadow(symbol, plan.stop, "stop", now)
                elif Decimal(str(bar.high)) >= plan.target: self.autopilot.close_shadow(symbol, plan.target, "target", now)
                elif now - datetime.fromisoformat(plan.candle_id.split(":", 1)[1]) >= self.plan_max_age: self.autopilot.close_shadow(symbol, Decimal(str(bar.close)), "timeout", now)
            except Exception as exc: self.last_error = f"{symbol}: {exc}"

    def status(self) -> str:
        r = self.last_report
        return (f"Runner läuft: {'ja' if self.running else 'nein'}\nScanintervall: {self.interval_seconds}s\nSymbole: {', '.join(self.symbols) or 'leer'}\n"
                f"Letzter Scan: {self.last_scan.isoformat() if self.last_scan else '–'}\nNächster Scan: {self.next_scan.isoformat() if self.next_scan else '–'}\n"
                f"Zustand: {r['state']}\nGeprüft: {', '.join(r['checked']) or '–'}\nAkzeptiert: {', '.join(r['accepted']) or '–'}\nAbgelehnt: {', '.join(f'{k}: {v}' for k,v in r['rejected'].items()) or '–'}\n"
                f"Letzter Runnerfehler: {self.last_error or '–'}\n" + ("⚠️ Kein persistenter DATABASE_URL-Store konfiguriert; Render-Neustarts können Zustände verlieren." if not os.getenv("DATABASE_URL") else "Persistenter DATABASE_URL-Store aktiv."))
