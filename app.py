from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backtester.data import load_csv, load_yfinance
from backtester.engine import BacktestConfig, run_backtest
from backtester.strategies import STRATEGIES, build_signal


st.set_page_config(page_title="Trading Strategy Backtester", layout="wide")
st.title("Trading Strategy Backtester")
st.caption(
    "Forschung und Ausbildung – keine Anlageberatung und kein Live-Trading. "
    "Vergangene Ergebnisse garantieren keine zukünftigen Gewinne."
)

with st.sidebar:
    st.header("Daten")
    source = st.radio("Datenquelle", ["Yahoo Finance", "CSV"])
    uploaded = None
    if source == "Yahoo Finance":
        ticker = st.text_input("Ticker", value="AAPL").strip().upper()
        period = st.selectbox("Zeitraum", ["5d", "1mo", "3mo", "6mo", "1y", "2y"], index=2)
        interval = st.selectbox(
            "Intervall",
            ["1m", "2m", "5m", "15m", "30m", "60m", "1d"],
            index=3,
        )
        prepost = st.checkbox("Vor-/Nachbörse einbeziehen", value=False)
    else:
        uploaded = st.file_uploader(
            "OHLCV-CSV",
            type=["csv"],
            help="Spalten: Date/Datetime, Open, High, Low, Close, Volume",
        )

    st.header("Strategie")
    strategy_name = st.selectbox("Strategie", list(STRATEGIES))
    allow_short = st.checkbox("Short-Positionen erlauben", value=True)
    params: dict[str, object] = {"allow_short": allow_short}

    if strategy_name == "VWAP Mean Reversion":
        params["z_window"] = st.number_input("Z-Score-Fenster", 5, 200, 20)
        params["entry_z"] = st.number_input("Einstieg ab |Z|", 0.1, 5.0, 1.5, 0.1)
        params["exit_z"] = st.number_input("Ausstieg bei |Z| ≤", 0.0, 2.0, 0.25, 0.05)
    elif strategy_name == "Opening Range Breakout":
        params["opening_bars"] = st.number_input("Balken der Opening Range", 1, 50, 4)
        params["breakout_buffer_bps"] = st.number_input(
            "Breakout-Puffer (Basispunkte)", 0.0, 100.0, 0.0, 0.5
        )
    else:
        params["fast_span"] = st.number_input("Schnelle EMA", 2, 100, 12)
        params["slow_span"] = st.number_input("Langsame EMA", 3, 300, 26)
        params["filter_window"] = st.number_input("Volatilitätsfilter", 5, 200, 20)
        params["minimum_strength_bps"] = st.number_input(
            "Mindeststärke (Basispunkte)", 0.0, 500.0, 0.0, 0.5
        )

    st.header("Kosten und Kapital")
    initial_capital = st.number_input("Startkapital", 100.0, 10_000_000.0, 10_000.0, 500.0)
    spread_bps = st.number_input("Spread (Basispunkte)", 0.0, 100.0, 2.0, 0.1)
    slippage_bps = st.number_input("Slippage je Order (Basispunkte)", 0.0, 100.0, 1.0, 0.1)
    commission = st.number_input("Kommission je Order", 0.0, 1000.0, 1.0, 0.25)
    run = st.button("Backtest starten", type="primary", use_container_width=True)


def percentage(value: float) -> str:
    return f"{value:.2%}"


if run:
    try:
        with st.spinner("Daten laden und Backtest berechnen …"):
            if source == "Yahoo Finance":
                data = load_yfinance(ticker, period, interval, prepost)
            else:
                if uploaded is None:
                    raise ValueError("Bitte zuerst eine CSV-Datei auswählen.")
                data = load_csv(uploaded)

            signal = build_signal(strategy_name, data, params)
            result = run_backtest(
                data,
                signal,
                BacktestConfig(
                    initial_capital=initial_capital,
                    spread_bps=spread_bps,
                    slippage_bps=slippage_bps,
                    commission_per_order=commission,
                ),
            )

        st.success(f"{len(data):,} Kursbalken ausgewertet.")

        metrics = result.metrics
        cards = st.columns(6)
        card_values = [
            ("Gesamtrendite", percentage(float(metrics["Gesamtrendite"]))),
            ("Buy-and-Hold", percentage(float(metrics["Buy-and-Hold"]))),
            ("Sharpe Ratio", f'{float(metrics["Sharpe Ratio"]):.2f}'),
            ("Max Drawdown", percentage(float(metrics["Max Drawdown"]))),
            ("Gewinnrate", percentage(float(metrics["Gewinnrate"]))),
            ("Trades", str(metrics["Trades"])),
        ]
        for col, (label, value) in zip(cards, card_values):
            col.metric(label, value)

        curve = result.equity_curve
        equity_fig = go.Figure()
        equity_fig.add_trace(
            go.Scatter(
                x=curve.index,
                y=curve["equity"],
                name="Strategie",
                mode="lines",
            )
        )
        buy_hold_equity = initial_capital * curve["close"] / curve["close"].iloc[0]
        equity_fig.add_trace(
            go.Scatter(
                x=curve.index,
                y=buy_hold_equity,
                name="Buy-and-Hold",
                mode="lines",
            )
        )
        equity_fig.update_layout(
            title="Equity-Kurve",
            xaxis_title="Zeit",
            yaxis_title="Kapital",
            legend_title="",
        )
        st.plotly_chart(equity_fig, use_container_width=True)

        drawdown_fig = go.Figure(
            go.Scatter(
                x=curve.index,
                y=curve["drawdown"],
                fill="tozeroy",
                name="Drawdown",
            )
        )
        drawdown_fig.update_layout(
            title="Drawdown",
            xaxis_title="Zeit",
            yaxis_tickformat=".1%",
        )
        st.plotly_chart(drawdown_fig, use_container_width=True)

        st.subheader("Alle Kennzahlen")
        metric_rows = []
        percentage_keys = {
            "Gesamtrendite",
            "Annualisierte Rendite",
            "Max Drawdown",
            "Annualisierte Volatilität",
            "Gewinnrate",
            "Marktexposition",
            "Buy-and-Hold",
            "Überrendite vs. Buy-and-Hold",
        }
        for key, value in metrics.items():
            if key in percentage_keys:
                display = percentage(float(value))
            elif isinstance(value, float):
                display = "∞" if math.isinf(value) else f"{value:,.2f}"
            else:
                display = str(value)
            metric_rows.append({"Kennzahl": key, "Wert": display})
        st.dataframe(pd.DataFrame(metric_rows), hide_index=True, use_container_width=True)

        st.subheader("Abgeschlossene Trades")
        if result.trades.empty:
            st.info("Die Strategie hat in diesem Zeitraum keinen Trade abgeschlossen.")
        else:
            trades_display = result.trades.copy()
            trades_display["return_pct"] = trades_display["return_pct"].map(lambda x: f"{x:.2%}")
            st.dataframe(trades_display, use_container_width=True, hide_index=True)
            st.download_button(
                "Trades als CSV herunterladen",
                result.trades.to_csv(index=False).encode("utf-8"),
                file_name="trades.csv",
                mime="text/csv",
            )

        st.download_button(
            "Equity-Kurve als CSV herunterladen",
            curve.to_csv().encode("utf-8"),
            file_name="equity_curve.csv",
            mime="text/csv",
        )

    except Exception as exc:
        st.error(str(exc))
        st.exception(exc)
else:
    st.info("Parameter links einstellen und den Backtest starten.")
