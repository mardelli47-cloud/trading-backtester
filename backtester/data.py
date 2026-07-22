from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd


REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a clean OHLCV frame with a sorted DatetimeIndex."""
    if frame is None or frame.empty:
        raise ValueError("Keine Kursdaten vorhanden.")

    data = frame.copy()

    if isinstance(data.columns, pd.MultiIndex):
        # yfinance may return either (field, ticker) or (ticker, field).
        known = {"open", "high", "low", "close", "adj close", "volume"}
        level0 = {str(v).strip().lower() for v in data.columns.get_level_values(0)}
        if level0 & known:
            data.columns = data.columns.get_level_values(0)
        else:
            data.columns = data.columns.get_level_values(-1)

    data.columns = [str(c).strip().lower().replace("_", " ") for c in data.columns]
    data = data.rename(columns={"adj close": "close"})

    if not isinstance(data.index, pd.DatetimeIndex):
        datetime_candidates = [
            c for c in data.columns
            if c in {"date", "datetime", "timestamp", "time"}
        ]
        if not datetime_candidates:
            raise ValueError(
                "CSV benötigt einen Datums-/Zeitindex oder eine Spalte "
                "'Date', 'Datetime' oder 'Timestamp'."
            )
        dt_col = datetime_candidates[0]
        data[dt_col] = pd.to_datetime(data[dt_col], errors="coerce", utc=True)
        data = data.set_index(dt_col)

    data.index = pd.to_datetime(data.index, errors="coerce", utc=True)
    data = data[~data.index.isna()]
    data.index = data.index.tz_convert(None)

    missing = REQUIRED_COLUMNS - set(data.columns)
    if missing:
        raise ValueError(f"Fehlende OHLCV-Spalten: {', '.join(sorted(missing))}")

    data = data[["open", "high", "low", "close", "volume"]].copy()
    for column in data.columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data = (
        data.replace([float("inf"), float("-inf")], pd.NA)
        .dropna(subset=["open", "high", "low", "close"])
        .sort_index()
    )
    data = data[~data.index.duplicated(keep="last")]
    data["volume"] = data["volume"].fillna(0.0)

    invalid = (
        (data["high"] < data[["open", "close", "low"]].max(axis=1))
        | (data["low"] > data[["open", "close", "high"]].min(axis=1))
        | (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    data = data.loc[~invalid]

    if len(data) < 30:
        raise ValueError("Zu wenige gültige Kursbalken; mindestens 30 werden benötigt.")

    return data


def load_csv(source: str | Path | BinaryIO | bytes) -> pd.DataFrame:
    if isinstance(source, bytes):
        source = BytesIO(source)
    frame = pd.read_csv(source)
    return normalize_ohlcv(frame)


def load_yfinance(
    ticker: str,
    period: str = "60d",
    interval: str = "15m",
    prepost: bool = False,
) -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance ist nicht installiert.") from exc

    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("Ticker darf nicht leer sein.")

    frame = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=True,
        prepost=prepost,
        progress=False,
        threads=False,
    )
    return normalize_ohlcv(frame)
