from __future__ import annotations

import argparse
import json
from pathlib import Path

from backtester.data import load_csv, load_yfinance
from backtester.engine import BacktestConfig, run_backtest
from backtester.strategies import build_signal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest common day-trading strategies.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--ticker", help="Yahoo Finance ticker, e.g. AAPL")
    source.add_argument("--csv", type=Path, help="OHLCV CSV file")

    parser.add_argument("--period", default="60d")
    parser.add_argument("--interval", default="15m")
    parser.add_argument(
        "--strategy",
        choices=["vwap", "orb", "momentum"],
        default="momentum",
    )
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--spread-bps", type=float, default=2.0)
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--commission", type=float, default=1.0)
    parser.add_argument("--no-short", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.ticker:
        data = load_yfinance(args.ticker, args.period, args.interval)
    else:
        data = load_csv(args.csv)

    strategy_map = {
        "vwap": "VWAP Mean Reversion",
        "orb": "Opening Range Breakout",
        "momentum": "Momentum",
    }
    signal = build_signal(
        strategy_map[args.strategy],
        data,
        {"allow_short": not args.no_short},
    )
    result = run_backtest(
        data,
        signal,
        BacktestConfig(
            initial_capital=args.capital,
            spread_bps=args.spread_bps,
            slippage_bps=args.slippage_bps,
            commission_per_order=args.commission,
        ),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result.equity_curve.to_csv(args.output_dir / "equity_curve.csv")
    result.trades.to_csv(args.output_dir / "trades.csv", index=False)
    (args.output_dir / "metrics.json").write_text(
        json.dumps(result.metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for key, value in result.metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
