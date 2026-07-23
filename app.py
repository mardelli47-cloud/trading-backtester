from __future__ import annotations

import math
import os

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

st.divider()
st.header("Echtzeit-Dashboard")
st.error("PAPER TRADING – KEIN ECHTGELD")
st.caption("Live-Trading ist im Code deaktiviert. Signale beruhen ausschließlich auf abgeschlossenen Kursbalken.")
with st.expander("Watchlist, Signale und Paper-Trading", expanded=False):
    from decimal import Decimal
    from backtester.broker import AlpacaPaperBroker
    from backtester.market_data import MarketDataService, MarketDataError
    from backtester.execution import PaperOrderService
    from backtester.risk import RiskManager, RiskSettings

    watchlist = st.text_input("Watchlist (kommagetrennt)", "AAPL,MSFT").upper()
    mode = st.radio("Modus", ["Analyse בלבד", "Paper Trading"], horizontal=True)
    st.caption("Paper Orders erfordern zusätzlich die ausdrückliche Aktivierung unten.")
    paper_confirmed = st.checkbox("Ich aktiviere ausschließlich Paper Trading", value=False)
    kill_switch = st.checkbox("Kill Switch: neue Orders sofort stoppen", value=True)
    risk_columns = st.columns(3)
    max_risk = risk_columns[0].number_input("Max. Risiko je Trade (%)", 0.1, 10.0, 1.0, 0.1)
    max_qty = risk_columns[1].number_input("Max. Positionsgröße", 1, 100000, 100, 1)
    max_loss = risk_columns[2].number_input("Max. Tagesverlust (%)", 0.1, 50.0, 3.0, 0.1)
    try:
        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        paper_value = os.getenv("ALPACA_PAPER", "true").lower()
        if paper_value != "true":
            raise ValueError("ALPACA_PAPER muss 'true' sein; Live-Modus ist gesperrt.")
        broker = AlpacaPaperBroker(api_key, secret_key, paper=True)
        market_data = MarketDataService(api_key, secret_key)
        account = broker.get_account()
        st.success("Verbindungsstatus: Paper-API verbunden")
        cards = st.columns(2)
        cards[0].metric("Kontostand", f"${account.equity:,.2f}")
        cards[1].metric("Kaufkraft", f"${account.buying_power:,.2f}")
        positions = broker.list_positions()
        orders = broker.list_orders(True)
        st.subheader("Signale")
        def dashboard_price(symbol):
            try: return f"${market_data.get_latest_price(symbol):,.2f}"
            except MarketDataError as exc: return f"Nicht verfügbar: {exc}"
        st.dataframe(pd.DataFrame([{
            "Symbol": symbol.strip(), "Aktueller Kurs": dashboard_price(symbol.strip()),
            "Signal": "neutral", "Signalzeit": "–", "Strategie": strategy_name,
            "Stärke": "–", "Position": next((str(p.qty) for p in positions if p.symbol == symbol.strip()), "0"),
            "Unrealisierter G/V": next((str(p.unrealized_pl) for p in positions if p.symbol == symbol.strip()), "0"),
        } for symbol in watchlist.split(",") if symbol.strip()]), hide_index=True, use_container_width=True)
        st.subheader("Offene Positionen")
        st.dataframe(pd.DataFrame([p.__dict__ for p in positions]), use_container_width=True, hide_index=True)
        st.subheader("Offene Orders / Trade-Historie")
        st.dataframe(pd.DataFrame([o.__dict__ for o in orders]), use_container_width=True, hide_index=True)
        if mode == "Paper Trading" and paper_confirmed:
            service = PaperOrderService(broker, RiskManager(RiskSettings(max_risk_per_trade_pct=Decimal(str(max_risk)), max_position_qty=Decimal(max_qty), max_daily_loss_pct=Decimal(str(max_loss))), account.equity, kill_switch), paper_enabled=True)
            st.info("Ordermaske ist nur während regulärer Handelszeiten aktiv; jede Order wird vor Übermittlung validiert.")
            with st.form("paper_order"):
                order_symbol = st.selectbox("Symbol für Paper-Order", [x.strip() for x in watchlist.split(",") if x.strip()] or ["AAPL"])
                order_side = st.selectbox("Seite", ["buy", "sell"])
                order_type = st.selectbox("Ordertyp", ["market", "limit"])
                order_qty = st.number_input("Stückzahl", min_value=1, value=1, step=1)
                limit_price = st.number_input("Limitpreis", min_value=0.01, value=1.00) if order_type == "limit" else None
                send_order = st.form_submit_button("Paper-Order validieren und übermitteln")
            if send_order:
                try:
                    from backtester.broker import OrderRequest
                    order = service.submit(OrderRequest(order_symbol, order_side, Decimal(order_qty), order_type, Decimal(str(limit_price)) if limit_price else None), Decimal(str(limit_price or 1)))
                    st.success(f"Paper-Order {order.status.value}: {order.client_order_id}")
                except Exception as order_exc:
                    st.error(f"Paper-Order nicht übermittelt: {order_exc}")
        else:
            st.info("Analysemodus aktiv: Es werden keine Orders übermittelt.")
    except Exception as exc:
        st.warning(f"Verbindungsstatus: nicht verbunden – {exc}")
        st.caption("Keine Schlüssel werden angezeigt oder protokolliert. Setze sie ausschließlich als Umgebungsvariablen.")
