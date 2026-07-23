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

## Paper-Trading-Autopilot (Version 1)

> **Paper Trading – kein echtes Geld. Reale Ausführungen können deutlich abweichen.**
> Der Autopilot ist keine Gewinnzusage und kann technisch *ausschließlich* den
> Alpaca-Paper-Endpunkt verwenden. Live-Trading, Wallets, Optionen, Shorts,
> Hebel, Martingale, Grid- und Nachkaufstrategien sind nicht implementiert.

Der Autopilot startet nach jedem Neustart sicher als `DISABLED` (ein zuvor
gespeicherter `PAPER_ACTIVE`-Zustand wird zu `PAUSED`). Nur Nutzer aus
`TELEGRAM_ALLOWED_USER_IDS` können ihn bedienen. `/autopilot start` verlangt
zwei Aufrufe und aktiviert zunächst nur `SHADOW`; `/autopilot paper` ist erst
nach 50 abgeschlossenen Shadow-Trades (oder einer explizit geprüften
Konfigurationsänderung) möglich. Verfügbare Zustände sind `DISABLED`, `SHADOW`,
`PAPER_ACTIVE`, `PAUSED`, `RISK_LOCKED` und `EMERGENCY_STOP`.

Telegram-Kommandos: `/autopilot [start|stop|pause|resume|shadow|paper|report|config|emergency]`,
`/profit today|week|month`, `/performance`, `/trades open|closed`, `/morning`
und `/close`. `emergency` aktiviert den Kill Switch; Positionen werden ohne
separate klare Schließbestätigung nicht blind liquidiert.

Der Scanner akzeptiert nur aktuelle, abgeschlossene Kerzen liquider US-Aktien
und ETFs (mindestens $5, kein OTC), reguläre Handelszeit, ausreichendes Volumen,
engen Spread und bestätigten Trend-Pullback oder Breakout. Datenlücken,
veraltete Daten und doppelte Kerzen führen fail-closed zu keiner Order. Die
Positionsgröße ist `Kontowert × 0,25 % / (Einstieg − Stop)` und zusätzlich auf
20 % pro Position, 50 % Gesamtexponierung, drei Positionen und fünf neue Trades
pro Tag begrenzt. Die zustands- und trade-plan-Persistenz liegt standardmäßig in
`autopilot_state.json` und sollte im Deployment auf dauerhaftem Storage liegen.

**Render-Hinweis:** Ein Render Free Web Service kann pausieren und ist daher
nicht zuverlässig für periodische Scans oder 24/7-Betrieb. Nutzen Sie für reale
regelmäßige Shadow-/Paper-Scans einen persistenten Worker plus externen Scheduler
und persistenten Datenträger; ein Webhook allein ist kein Scheduler.

## Echtzeit-Analyse und Alpaca Paper Trading

> **PAPER TRADING – KEIN ECHTGELD.** Das Modul unterstützt ausschließlich den
> Alpaca-Paper-Endpunkt. Der Live-Endpunkt kann nicht aktiviert werden. Paper
> Trading simuliert Ausführungen und ist keine Gewinngarantie.

1. Einen kostenlosen [Alpaca Paper Account](https://alpaca.markets/) erstellen und
   dort Paper-API-Schlüssel erzeugen.
2. Die Schlüssel ausschließlich als `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` und
   `ALPACA_PAPER=true` in der Umgebung bzw. im Secret Store setzen. Für Kurse
   und historische Bars wird der getrennte Alpaca-Market-Data-Client verwendet;
   `ALPACA_DATA_FEED=iex` ist der sichere Standard für kostenlose Paper-Konten.
   `sip` nur bei bestätigter Berechtigung setzen. Die Schlüssel dürfen
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
2. `TELEGRAM_ALLOWED_USER_IDS` als numerische Whitelist setzen und
   `ALPACA_PAPER=true` beibehalten. Erlaubt sind z. B. `123456789`,
   `123456789, 987654321`, `"123456789"` oder `[123456789]`. Die Prüfung nutzt
   bei Commands, Text-/Reply-Buttons, Inline-Buttons und Dialogen ausschließlich
   die Telegram-**User-ID** (`effective_user.id`), nicht die Chat-ID. Mit
   `/whoami` kann ein erlaubter Nutzer die IDs und den Status prüfen.
3. Lokal (nur Entwicklung): `python telegram_worker.py --local-polling`.
4. Bei **Render** einen **Web Service** (keinen Background Worker) verwenden: Der
   Startbefehl ist `python telegram_worker.py` und Render setzt `PORT`
   automatisch. Der Worker bindet seinen PTB-Webhook-Server an `0.0.0.0:$PORT`,
   damit Render den offenen Port erkennen und Telegram ihn erreichen kann.
   `TELEGRAM_WEBHOOK_URL` im Secret Store auf die öffentliche HTTPS-URL des
   Services **ohne** abschließendes `/telegram` setzen; der Worker ergänzt den
   Webhook-Pfad selbst. Das mitgelieferte `render.yaml` enthält diese Einstellungen.
   Streamlit Community Cloud ist hierfür ungeeignet, weil sie keinen dauerhaft
   laufenden Web-Service garantiert.

Beim Start prüft der Worker die Werte, die als HTTP-Header verwendet werden,
bevor er einen Alpaca-Client oder Telegram-Webhook erstellt. Dabei werden nur
die Headernamen geloggt: `APCA-API-KEY-ID`, `APCA-API-SECRET-KEY` und (falls
gesetzt) `X-Telegram-Bot-Api-Secret-Token`. Nicht-ASCII-Zeichen werden vor dem
Netzwerkzugriff mit dem Namen der verantwortlichen Umgebungsvariable abgewiesen;
die Werte selbst erscheinen nie in Logs oder Fehlermeldungen.

Unterstützt werden `/start`, `/help`, `/status`, `/signals`, `/positions`,
`/orders`, `/account`, `/risk`, `/pause`, `/resume`, `/kill` und `/watchlist`.
Unbekannte Nutzer bekommen weder Konto- noch Orderdaten. Rohfehler und Secrets
werden nie an Telegram übertragen; Netzwerkfehler führen nie zu einer
Bestellwiederholung.

### Telegram Trading-App – Version 1

Nach `/start` oder `/menu` bleibt dieses Hauptmenü sichtbar:

```text
📊 Analyse | 🔎 Scanner       ⭐ Watchlist | 🌅 Morning
💼 Konto   | 📈 Positionen    🧾 Orders    | ⚙️ Risiko
🤖 Autopilot | 📔 Journal     📅 Termine   | ⚙️ Einstellungen
🔄 Aktualisieren | ❓ Hilfe
```

Alle bisherigen Slash-Befehle bleiben verfügbar; ergänzt wurden `/menu`,
`/daily`, `/midday`, `/scan`, `/plan SYMBOL`, `/upcoming`, `/journal`,
`/compact` und `/detailed`. Eine Nachricht mit einem einzelnen, validen Symbol
wie `AAPL` startet eine Analyse. Analyse-, Konto-, Watchlist-, Scanner- und
Autopilot-Ausgaben enthalten kontextbezogene Inline-Buttons. Eingaben über
Buttons (Analyse und Watchlist) laufen über zeitlich begrenzte Dialoge.

Die Watchlist und die Ansichtsoption werden über eine Storage-Abstraktion
gespeichert: lokal SQLite (`telegram_state.sqlite3`), bei gesetztem
`DATABASE_URL` PostgreSQL. Für Render ist eine persistente PostgreSQL-Datenbank
erforderlich; ohne diese ist lokaler Dateispeicher nach einem Neustart nicht
garantiert. Der gemeinsame `MarketDataService` lädt letzte Trades/Quotes und
historische Aktienbars über die **Alpaca Market Data API**, nicht über den
Trading-Endpunkt. Einzelanalysen verwenden mindestens 100 abgeschlossene Tages-
und, soweit verfügbar, 15-Minuten-Bars. Die laufende Kerze wird nicht als
bestätigtes Signal verwendet. Fehlen Intraday-Bars, bleibt die Tagesanalyse
sichtbar und markiert den fehlenden Intraday-Teil; bei Daten-, Berechtigungs-,
Rate-Limit- und Timeout-Fehlern werden keine Kurse oder Scores erfunden.

`/account`, `/positions`, `/orders` und `/risk` geben ausschließlich die
jeweiligen Daten des Paper-Brokers bzw. die aktiven Risikolimits aus. `/signals`
zeigt nur Signale aus abgeschlossenen Balken an. Mit `/watchlist AAPL,MSFT` wird
die Watchlist für die Signalanzeige gesetzt; ohne Argument zeigt der Befehl die
aktuelle Watchlist an.

## Internationale Telegram-Analyse

Der Telegram-Worker trennt **Datenanbieter** und **Handelsanbieter**. US-Aktien/ETFs
bleiben bei Alpaca Market Data, Kryptowerte bleiben bei Alpaca Crypto. Für deutsche,
europäische und sonstige internationale Aktien, Forex, Indizes und Rohstoffreferenzen
ist [Twelve Data](https://twelvedata.com/) der einzige primäre offizielle Anbieter:
`TWELVE_DATA_API_KEY` wird ausschließlich über die Umgebung gelesen. Die dokumentierte
Symbolsuche und Time-Series-API erlauben eine explizite Symbolauflösung ohne eine
Notierung stillschweigend zu ersetzen.

Optional kann `ENABLE_YFINANCE_FALLBACK=true` gesetzt werden. Der Fallback ist
analyse-only, gecacht und mit Timeout versehen; Yahoo/yfinance kann verzögert sein oder
Datenlücken aufweisen und wird nie als Alpaca-Orderpreis verwendet. Ohne Provider-Key
läuft der Bot weiter und meldet verständlich, dass der globale Anbieter deaktiviert ist.
Weitere Einstellungen sind `MARKET_DATA_CACHE_TTL_SECONDS`,
`INSTRUMENT_SEARCH_CACHE_TTL_SECONDS`, `PROVIDER_REQUEST_TIMEOUT_SECONDS` und
`PROVIDER_MAX_RETRIES`.

Beispiele: `IFX.DE` ist **Infineon AG – Xetra – EUR**, während `IFNNY` eine eigene
OTC/ADR-Notierung bleibt; weder wird durch die andere ersetzt. `/plan IFX.DE`,
`/watchlist add EUR/USD`, `/watchlist add DAX` und `/watchlist add GOLD` verwenden
kanonische Instrumente. Unterstützte Referenzwerte umfassen DAX, Euro Stoxx 50, FTSE
100, CAC 40, EUR/USD, GBP/USD, USD/JPY sowie Gold/Silber/WTI/Brent-Future-Referenzen.

Diese Instrumente tragen stets `analysis_only=true` und `paper_tradable=false`.
Telegram zeigt deshalb keine Paper-Buy/Sell-Schaltflächen und blockiert einen
Orderversuch technisch. Indizes sind Analyseinstrumente; Future-Referenzen sind weder
Spotpreise noch direkt handelbare Alpaca-Paper-Instrumente. Compact- und Detailed-
Ausgaben zeigen Anbieter, Zeitstempel, Währung, Zeitzone, Verzögerung und
Datenqualität. Bei fehlenden Intraday-Daten bleibt die Tagesanalyse verfügbar; bei
veralteten oder unzureichenden Daten wird keine Empfehlung erfunden. Bei Rate Limits
werden nur noch gültige Cache-Ergebnisse als solche verwendet.

**Render:** Setzen Sie `TWELVE_DATA_API_KEY` und optional
`ENABLE_YFINANCE_FALLBACK=true` im Render Secret Store, nicht in Dateien oder Logs.
Deployen Sie anschließend den bestehenden Web Service/Worker neu und prüfen Sie
`/plan IFX.DE`, `/plan EUR/USD` sowie `/watchlist add DAX`. Provider-Keys, Nutzer- und
Kontodaten werden weder im Health-Status noch in Telegram-Fehlern ausgegeben.

### Paper-Autopilot

Der Autopilot verarbeitet ausschließlich Alpaca-Marktdaten und Alpaca-Paper-Orders.
`AUTOPILOT_SCAN_INTERVAL_SECONDS` (mindestens 60, Standard 300),
`AUTOPILOT_SYMBOLS`, `AUTOPILOT_MIN_SHADOW_TRADES` (Standard 20, mindestens 5),
`AUTOPILOT_MAX_SYMBOLS` (maximal 20) und `AUTOPILOT_PLAN_MAX_AGE_MINUTES`
konfigurieren den begrenzten Scan. Der Runner startet im Telegram-Application-Lifecycle;
`/autopilot scan` führt zusätzlich genau einen manuellen Zyklus aus. Shadow-Positionen
werden bei Stop, Ziel (bei gleicher Kerze konservativ zuerst Stop) oder Timeout geschlossen
und persistent ausgewertet. Render Free kann einschlafen; für zuverlässige Überwachung ist
ein Always-on-Service oder Background Worker erforderlich.
