# Trading Strategy Backtester

Ein lokaler Backtest-Simulator für drei verbreitete Daytrading-Ansätze:

- VWAP Mean Reversion
- Opening Range Breakout
- EMA Momentum

Das Projekt berechnet realistische Handelskosten, Trade-Statistiken, Sharpe Ratio,
Max Drawdown, Equity-Kurve und einen Vergleich zu Buy-and-Hold.

> **Wichtig:** Forschungs- und Lernsoftware. Keine Anlageberatung. Kein Live-Trading.
> Historische Ergebnisse sagen nichts Sicheres über zukünftige Ergebnisse aus.

## Sicherheits- und Qualitätsregeln

- Kein Brokerzugang und keine echten Orders.
- Signale eines Balkens werden erst für den folgenden Kurszeitraum verwendet.
- Spread, Slippage und feste Kommission werden getrennt modelliert.
- Offene Positionen werden am Ende des Datensatzes geschlossen.
- CSV-Daten werden validiert und bereinigt.
- Jede Strategie kann Long-only oder Long/Short getestet werden.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Dashboard starten

```bash
streamlit run app.py
```

Danach Ticker, Zeitraum, Intervall, Strategie und Kosten im Browser auswählen.

## CLI-Beispiele

Yahoo-Finance-Daten:

```bash
python cli.py --ticker AAPL --period 60d --interval 15m --strategy momentum
```

CSV-Datei:

```bash
python cli.py --csv meine_daten.csv --strategy vwap --no-short
```

Ergebnisse werden nach `outputs/` geschrieben:

- `metrics.json`
- `trades.csv`
- `equity_curve.csv`

## CSV-Format

```csv
Datetime,Open,High,Low,Close,Volume
2026-01-02 09:30:00,100.0,100.5,99.8,100.2,15000
```

## Tests

```bash
pytest -q
```

## Was als Nächstes sinnvoll ist

1. Walk-forward-Analyse statt nur eines einzigen Zeitraums.
2. Out-of-sample-Test und Parameterstabilitätskarten.
3. Monte-Carlo-Reihenfolge-Simulation der Trades.
4. Zeitabhängige Spreads und Volumen-/Liquiditätsfilter.
5. Separate Long-/Short-Kennzahlen.
6. Paper-Trading-Adapter erst nach bestandenen Qualitätsprüfungen.
7. Live-Trading ausschließlich mit harten Risiko-Limits und manueller Freigabe.

## Echtzeit-Analyse und Alpaca Paper Trading

> **PAPER TRADING – KEIN ECHTGELD.** Das Modul unterstützt ausschließlich den
> Alpaca-Paper-Endpunkt. Der Live-Endpunkt kann nicht aktiviert werden. Paper
> Trading simuliert Ausführungen und ist keine Gewinngarantie.

1. Einen kostenlosen [Alpaca Paper Account](https://alpaca.markets/) erstellen und
   dort Paper-API-Schlüssel erzeugen.
2. Die Schlüssel ausschließlich als `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` und
   `ALPACA_PAPER=true` in der Umgebung bzw. im Secret Store setzen. Sie dürfen
   weder in `secrets.toml` noch im Quellcode stehen, committed oder geloggt werden.

Starten Sie das Dashboard mit `streamlit run app.py`. Im Bereich **Echtzeit-Dashboard**
ist der Standard **Analyse בלבד**; Paper Orders benötigen eine ausdrückliche zweite
Bestätigung. Die Oberfläche zeigt Paper-Konto, Positionen, offene Orders und den
Verbindungsstatus. WebSocket-Marktdaten werden bei Abbruch mit begrenztem Backoff
wieder verbunden. Signale für Momentum, VWAP Mean Reversion und Opening Range
Breakout werden nur aus abgeschlossenen Balken berechnet.

Vor jeder Paper-Order erzwingen Idempotenzschutz, reguläre US-Handelszeiten,
vorhandene offene Orders/Positionen sowie Positions-, Kaufkraft-, Tagesverlust-,
Cooldown- und Kill-Switch-Prüfungen eine fail-closed Validierung. Netzwerkfehler
werden **nicht** automatisch mit einer weiteren Order beantwortet.

## Sicherer Telegram-Paper-Trading-Worker

> **PAPER TRADING – KEIN ECHTGELD.** Der Telegram-Worker kann ausschließlich den
> Alpaca-Paper-Endpunkt ansprechen. Er ist standardmäßig ein Analyse- und
> Benachrichtigungskanal; jede Order benötigt zwei getrennte Inline-Bestätigungen
> innerhalb von 60 Sekunden. Der Kill Switch sperrt neue Orders sofort.

1. `cp .env.example .env` und **nur lokal bzw. im Secret Store** befüllen.
   Alle Werte werden ausschließlich aus Umgebungsvariablen gelesen; weder
   Streamlit-Secrets noch Quellcode enthalten Schlüssel.
2. `TELEGRAM_ALLOWED_USER_IDS` als kommagetrennte numerische Whitelist setzen und
   `ALPACA_PAPER=true` beibehalten. Alles andere wird fail-closed abgewiesen.
3. Lokal (nur Entwicklung): `python telegram_worker.py --local-polling`.
4. Dauerhaft: einen Python-Worker bei Render oder Railway betreiben, die
   Umgebungsvariablen in dessen Secret Store hinterlegen und `TELEGRAM_WEBHOOK_URL`
   auf die öffentliche HTTPS-URL setzen. Startbefehl: `python telegram_worker.py`.
   Streamlit Community Cloud ist hierfür ungeeignet, weil sie keinen dauerhaft
   laufenden Worker garantiert.

Unterstützt werden `/start`, `/help`, `/status`, `/signals`, `/positions`,
`/orders`, `/account`, `/risk`, `/pause`, `/resume`, `/kill` und `/watchlist`.
Unbekannte Nutzer bekommen weder Konto- noch Orderdaten. Rohfehler und Secrets
werden nie an Telegram übertragen; Netzwerkfehler führen nie zu einer
Bestellwiederholung.
