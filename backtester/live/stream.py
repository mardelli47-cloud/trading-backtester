"""Reconnectable Alpaca websocket adapter. It is data-only and never submits orders."""
from __future__ import annotations
import logging, os, time
from collections.abc import Callable
class AlpacaMarketDataStream:
    def __init__(self, symbols:list[str], on_bar:Callable[[object],None], api_key:str|None=None, secret_key:str|None=None):
        self.symbols=symbols; self.on_bar=on_bar; self.api_key=api_key or os.getenv("ALPACA_API_KEY",""); self.secret_key=secret_key or os.getenv("ALPACA_SECRET_KEY",""); self.connected=False; self.error: str|None=None; self._stopped=False
    def stop(self): self._stopped=True
    def run_forever(self, max_retries:int|None=None):
        if not self.api_key or not self.secret_key: self.error="Alpaca API-Schlüssel fehlen."; return
        attempt=0
        while not self._stopped and (max_retries is None or attempt<=max_retries):
            try:
                from alpaca.data.live import StockDataStream
                stream=StockDataStream(self.api_key,self.secret_key)
                async def handle(bar): self.on_bar(bar)
                stream.subscribe_bars(handle,*self.symbols); self.connected=True; self.error=None; stream.run()
            except Exception as exc:
                self.connected=False; self.error=f"WebSocket getrennt: {exc}"; logging.warning("Alpaca market-data reconnect scheduled: %s", type(exc).__name__)
                attempt+=1
                if not self._stopped and (max_retries is None or attempt<=max_retries): time.sleep(min(30,2**attempt))
