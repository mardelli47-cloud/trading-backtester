import numpy as np
import pandas as pd

from backtester.engine import BacktestConfig, run_backtest
from backtester.metrics import max_drawdown
from backtester.strategies import build_signal


def sample_data(rows: int = 120) -> pd.DataFrame:
    index = pd.date_range("2026-01-02 09:30", periods=rows, freq="15min")
    close = 100 * np.cumprod(1 + np.sin(np.arange(rows) / 8) * 0.001)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(rows, 1_000),
        },
        index=index,
    )


def test_costs_reduce_equity():
    data = sample_data()
    signal = pd.Series(1, index=data.index)

    free = run_backtest(
        data,
        signal,
        BacktestConfig(spread_bps=0, slippage_bps=0, commission_per_order=0),
    )
    costly = run_backtest(
        data,
        signal,
        BacktestConfig(spread_bps=10, slippage_bps=5, commission_per_order=2),
    )

    assert costly.equity_curve["equity"].iloc[-1] < free.equity_curve["equity"].iloc[-1]


def test_next_bar_execution_avoids_same_bar_profit():
    index = pd.date_range("2026-01-01", periods=4, freq="D")
    data = pd.DataFrame(
        {
            "open": [100, 200, 200, 200],
            "high": [100, 200, 200, 200],
            "low": [100, 200, 200, 200],
            "close": [100, 200, 200, 200],
            "volume": [1000] * 4,
        },
        index=index,
    )
    # Signal appears only after the 100 -> 200 jump. A correct engine cannot earn it.
    signal = pd.Series([0, 1, 0, 0], index=index)
    result = run_backtest(
        data,
        signal,
        BacktestConfig(spread_bps=0, slippage_bps=0, commission_per_order=0),
    )
    assert result.metrics["Gesamtrendite"] == 0


def test_max_drawdown():
    equity = pd.Series([100.0, 120.0, 90.0, 110.0])
    dd, series = max_drawdown(equity)
    assert round(dd, 4) == -0.25
    assert round(series.iloc[2], 4) == -0.25


def test_all_strategies_return_valid_signal():
    data = sample_data(200)
    for name in ["VWAP Mean Reversion", "Opening Range Breakout", "Momentum"]:
        signal = build_signal(name, data, {"allow_short": True})
        assert signal.index.equals(data.index)
        assert set(signal.unique()).issubset({-1, 0, 1})
