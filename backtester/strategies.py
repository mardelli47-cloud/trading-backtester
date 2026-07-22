from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd


SignalBuilder = Callable[[pd.DataFrame], pd.Series]


def _persist_positions(
    long_entry: pd.Series,
    short_entry: pd.Series,
    exit_condition: pd.Series,
    force_flat: pd.Series | None = None,
) -> pd.Series:
    position = 0
    values: list[int] = []

    for idx in long_entry.index:
        if force_flat is not None and bool(force_flat.loc[idx]):
            position = 0
        elif position == 0:
            if bool(long_entry.loc[idx]):
                position = 1
            elif bool(short_entry.loc[idx]):
                position = -1
        elif bool(exit_condition.loc[idx]):
            position = 0
        values.append(position)

    return pd.Series(values, index=long_entry.index, dtype="int8")


def vwap_mean_reversion(
    data: pd.DataFrame,
    z_window: int = 20,
    entry_z: float = 1.5,
    exit_z: float = 0.25,
    allow_short: bool = True,
) -> pd.Series:
    """Intraday VWAP mean reversion with rolling z-score bands."""
    typical = (data["high"] + data["low"] + data["close"]) / 3.0
    dates = pd.Series(data.index.date, index=data.index)
    pv = typical * data["volume"].clip(lower=0)
    cumulative_pv = pv.groupby(dates).cumsum()
    cumulative_volume = data["volume"].clip(lower=0).groupby(dates).cumsum()
    vwap = cumulative_pv / cumulative_volume.replace(0, np.nan)
    vwap = vwap.fillna(typical)

    deviation = data["close"] - vwap
    rolling_std = deviation.rolling(max(5, int(z_window)), min_periods=5).std()
    z_score = deviation / rolling_std.replace(0, np.nan)

    long_entry = z_score < -abs(entry_z)
    short_entry = (z_score > abs(entry_z)) if allow_short else pd.Series(False, index=data.index)
    exit_condition = z_score.abs() <= abs(exit_z)

    signal = _persist_positions(long_entry, short_entry, exit_condition)
    # Intraday strategy: do not deliberately carry a signal into the next session.
    session_end = dates.ne(dates.shift(-1))
    signal.loc[session_end] = 0
    return signal.rename("signal")


def opening_range_breakout(
    data: pd.DataFrame,
    opening_bars: int = 4,
    breakout_buffer_bps: float = 0.0,
    allow_short: bool = True,
) -> pd.Series:
    """Breakout of each session's first N bars, flat at session end."""
    opening_bars = max(1, int(opening_bars))
    dates = pd.Series(data.index.date, index=data.index)
    bar_number = data.groupby(dates).cumcount()

    opening_mask = bar_number < opening_bars
    session_high = data["high"].where(opening_mask).groupby(dates).transform("max")
    session_low = data["low"].where(opening_mask).groupby(dates).transform("min")

    buffer = abs(float(breakout_buffer_bps)) / 10_000.0
    can_trade = bar_number >= opening_bars
    long_entry = can_trade & (data["close"] > session_high * (1.0 + buffer))
    short_entry = (
        can_trade & (data["close"] < session_low * (1.0 - buffer))
        if allow_short
        else pd.Series(False, index=data.index)
    )

    session_end = dates.ne(dates.shift(-1))
    signal = _persist_positions(
        long_entry=long_entry,
        short_entry=short_entry,
        exit_condition=session_end,
        force_flat=session_end,
    )
    signal.loc[opening_mask] = 0
    signal.loc[session_end] = 0
    return signal.rename("signal")


def momentum(
    data: pd.DataFrame,
    fast_span: int = 12,
    slow_span: int = 26,
    filter_window: int = 20,
    minimum_strength_bps: float = 0.0,
    allow_short: bool = True,
) -> pd.Series:
    """EMA momentum with a volatility-scaled confirmation filter."""
    fast_span = max(2, int(fast_span))
    slow_span = max(fast_span + 1, int(slow_span))
    filter_window = max(5, int(filter_window))

    fast = data["close"].ewm(span=fast_span, adjust=False).mean()
    slow = data["close"].ewm(span=slow_span, adjust=False).mean()
    strength = (fast / slow - 1.0) * 10_000.0
    rolling_vol_bps = (
        data["close"].pct_change().rolling(filter_window).std() * 10_000.0
    ).fillna(0.0)
    threshold = np.maximum(abs(float(minimum_strength_bps)), rolling_vol_bps * 0.10)

    signal = pd.Series(0, index=data.index, dtype="int8")
    signal.loc[strength > threshold] = 1
    if allow_short:
        signal.loc[strength < -threshold] = -1

    warmup = max(slow_span, filter_window)
    signal.iloc[:warmup] = 0
    return signal.rename("signal")


STRATEGIES: dict[str, Callable[..., pd.Series]] = {
    "VWAP Mean Reversion": vwap_mean_reversion,
    "Opening Range Breakout": opening_range_breakout,
    "Momentum": momentum,
}


def build_signal(
    strategy_name: str,
    data: pd.DataFrame,
    parameters: dict[str, Any] | None = None,
) -> pd.Series:
    try:
        strategy = STRATEGIES[strategy_name]
    except KeyError as exc:
        raise ValueError(
            f"Unbekannte Strategie: {strategy_name}. "
            f"Verfügbar: {', '.join(STRATEGIES)}"
        ) from exc
    signal = strategy(data, **(parameters or {}))
    return signal.reindex(data.index).fillna(0).clip(-1, 1).astype("int8")
