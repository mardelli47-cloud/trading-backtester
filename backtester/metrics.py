from __future__ import annotations

import math

import numpy as np
import pandas as pd


def infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 3:
        return 252.0
    deltas = index.to_series().diff().dropna()
    median_seconds = float(deltas.dt.total_seconds().median())
    if not math.isfinite(median_seconds) or median_seconds <= 0:
        return 252.0

    days = median_seconds / 86_400.0
    if days >= 0.75:
        return 252.0

    # Assume regular US-style trading sessions for annualization only.
    bars_per_day = max(1.0, (6.5 * 3600.0) / median_seconds)
    return 252.0 * bars_per_day


def max_drawdown(equity: pd.Series) -> tuple[float, pd.Series]:
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min()), drawdown


def calculate_metrics(
    equity: pd.Series,
    positions: pd.Series,
    trades: pd.DataFrame,
    initial_capital: float,
    buy_hold_return: float,
) -> dict[str, float | int]:
    returns = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    periods_per_year = infer_periods_per_year(equity.index)

    total_return = float(equity.iloc[-1] / initial_capital - 1.0)
    elapsed_years = max(
        (equity.index[-1] - equity.index[0]).total_seconds()
        / (365.25 * 86_400.0),
        1.0 / periods_per_year,
    )
    annual_return = (1.0 + total_return) ** (1.0 / elapsed_years) - 1.0 \
        if total_return > -1 else -1.0

    volatility = float(returns.std(ddof=0) * np.sqrt(periods_per_year)) \
        if len(returns) else 0.0
    sharpe = (
        float(returns.mean() / returns.std(ddof=0) * np.sqrt(periods_per_year))
        if len(returns) > 1 and returns.std(ddof=0) > 0
        else 0.0
    )
    maximum_drawdown, _ = max_drawdown(equity)

    if trades.empty:
        winning = pd.Series(dtype=float)
        losing = pd.Series(dtype=float)
        win_rate = 0.0
        profit_factor = 0.0
        avg_trade = 0.0
    else:
        pnl = trades["pnl"].astype(float)
        winning = pnl[pnl > 0]
        losing = pnl[pnl < 0]
        win_rate = float((pnl > 0).mean())
        gross_profit = float(winning.sum())
        gross_loss = abs(float(losing.sum()))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
            float("inf") if gross_profit > 0 else 0.0
        )
        avg_trade = float(pnl.mean())

    return {
        "Endkapital": float(equity.iloc[-1]),
        "Gesamtrendite": total_return,
        "Annualisierte Rendite": float(annual_return),
        "Sharpe Ratio": sharpe,
        "Max Drawdown": maximum_drawdown,
        "Annualisierte Volatilität": volatility,
        "Trades": int(len(trades)),
        "Gewinnrate": win_rate,
        "Profit Factor": float(profit_factor),
        "Ø Trade-PnL": avg_trade,
        "Marktexposition": float((positions != 0).mean()),
        "Buy-and-Hold": float(buy_hold_return),
        "Überrendite vs. Buy-and-Hold": total_return - float(buy_hold_return),
    }
