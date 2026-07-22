"""Closed-bar-only real-time signal calculations."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
from backtester.strategies import build_signal
@dataclass(frozen=True)
class LiveSignal:
    symbol:str; price:float; signal:int; signal_time:pd.Timestamp; strategy:str; strength:float
class ClosedBarAnalyzer:
    def __init__(self, strategy: str, parameters: dict[str,object]|None=None): self.strategy=strategy; self.parameters=parameters or {}; self._bars:dict[str,pd.DataFrame]={}
    def add_closed_bar(self,symbol:str,bar:dict[str,object])->LiveSignal|None:
        """Accept only explicitly final bars, so in-progress prices never affect a signal."""
        if not bool(bar.get("is_closed",False)): return None
        time=pd.Timestamp(bar["timestamp"]); row=pd.DataFrame([{k:bar[k] for k in ("open","high","low","close","volume")}],index=[time])
        data=pd.concat([self._bars.get(symbol,pd.DataFrame()),row]).sort_index(); data=data[~data.index.duplicated(keep="last")]; self._bars[symbol]=data.tail(1000)
        # build_signal needs history. A zero signal is explicit until the warm-up completes.
        if len(data)<30: return LiveSignal(symbol,float(row.close.iloc[0]),0,time,self.strategy,0.0)
        signal=build_signal(self.strategy,data,self.parameters); value=int(signal.iloc[-1]); strength=float(abs(data.close.pct_change().iloc[-1] or 0)*10_000)
        return LiveSignal(symbol,float(row.close.iloc[0]),value,time,self.strategy,strength)
