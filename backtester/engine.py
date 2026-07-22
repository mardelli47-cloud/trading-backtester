from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import calculate_metrics, max_drawdown


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 10_000.0
    spread_bps: float = 2.0
    slippage_bps: float = 1.0
    commission_per_order: float = 1.0

    def validate(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("Startkapital muss positiv sein.")
        if min(self.spread_bps, self.slippage_bps, self.commission_per_order) < 0:
            raise ValueError("Kostenparameter dürfen nicht negativ sein.")


@dataclass
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float | int]
    signal: pd.Series


def _order_cost(equity: float, config: BacktestConfig) -> float:
    # Half the quoted spread is crossed on each individual buy/sell order.
    variable_rate = (config.spread_bps / 2.0 + config.slippage_bps) / 10_000.0
    return equity * variable_rate + config.commission_per_order


def run_backtest(
    data: pd.DataFrame,
    signal: pd.Series,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run a close-to-close, next-bar-execution backtest.

    A signal observed on bar t becomes the target position for the return
    interval from close[t] to close[t+1]. This prevents same-bar look-ahead.
    """
    config = config or BacktestConfig()
    config.validate()

    if len(data) < 3:
        raise ValueError("Mindestens drei Kursbalken werden benötigt.")
    if not data.index.equals(signal.index):
        signal = signal.reindex(data.index).fillna(0)

    signal = signal.fillna(0).clip(-1, 1).astype(int)
    close = data["close"].astype(float)

    equity = float(config.initial_capital)
    current_position = 0
    entry_equity: float | None = None
    entry_time: pd.Timestamp | None = None
    entry_price: float | None = None
    trade_direction: int | None = None

    equity_values = [equity]
    position_values = [0]
    cost_values = [0.0]
    trade_rows: list[dict[str, object]] = []

    for i in range(1, len(data)):
        execution_time = data.index[i - 1]
        execution_price = float(close.iloc[i - 1])
        desired_position = int(signal.iloc[i - 1])
        period_cost = 0.0

        if desired_position != current_position:
            if current_position != 0:
                close_cost = min(equity, _order_cost(equity, config))
                equity -= close_cost
                period_cost += close_cost

                pnl = equity - float(entry_equity)
                trade_rows.append(
                    {
                        "entry_time": entry_time,
                        "exit_time": execution_time,
                        "direction": "Long" if trade_direction == 1 else "Short",
                        "entry_price": entry_price,
                        "exit_price": execution_price,
                        "pnl": pnl,
                        "return_pct": pnl / float(entry_equity)
                        if entry_equity else 0.0,
                        "exit_reason": "Reversal" if desired_position != 0 else "Signal",
                    }
                )
                current_position = 0
                entry_equity = None

            if desired_position != 0 and equity > 0:
                open_cost = min(equity, _order_cost(equity, config))
                equity -= open_cost
                period_cost += open_cost
                current_position = desired_position
                entry_equity = equity
                entry_time = execution_time
                entry_price = execution_price
                trade_direction = desired_position

        if equity <= 0:
            equity = 0.0
            current_position = 0
        else:
            price_return = float(close.iloc[i] / close.iloc[i - 1] - 1.0)
            equity *= max(0.0, 1.0 + current_position * price_return)

        equity_values.append(equity)
        position_values.append(current_position)
        cost_values.append(period_cost)

    # Liquidate any remaining position at the final close.
    if current_position != 0 and equity > 0:
        final_cost = min(equity, _order_cost(equity, config))
        equity -= final_cost
        cost_values[-1] += final_cost
        equity_values[-1] = equity
        pnl = equity - float(entry_equity)
        trade_rows.append(
            {
                "entry_time": entry_time,
                "exit_time": data.index[-1],
                "direction": "Long" if trade_direction == 1 else "Short",
                "entry_price": entry_price,
                "exit_price": float(close.iloc[-1]),
                "pnl": pnl,
                "return_pct": pnl / float(entry_equity) if entry_equity else 0.0,
                "exit_reason": "End of data",
            }
        )
        position_values[-1] = 0

    curve = pd.DataFrame(
        {
            "equity": equity_values,
            "position": position_values,
            "cost": cost_values,
            "close": close.values,
            "signal": signal.values,
        },
        index=data.index,
    )
    _, curve["drawdown"] = max_drawdown(curve["equity"])
    curve["strategy_return"] = curve["equity"].pct_change().fillna(0.0)

    trades = pd.DataFrame(trade_rows)
    buy_hold_return = float(close.iloc[-1] / close.iloc[0] - 1.0)
    metrics = calculate_metrics(
        equity=curve["equity"],
        positions=curve["position"],
        trades=trades,
        initial_capital=config.initial_capital,
        buy_hold_return=buy_hold_return,
    )

    return BacktestResult(
        equity_curve=curve,
        trades=trades,
        metrics=metrics,
        signal=signal,
    )
