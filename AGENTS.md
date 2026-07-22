# Codex Arbeitsanweisung

## Ziel

Dieses Repository ist ein transparenter, reproduzierbarer Backtest-Simulator.
Es ist ausdrücklich kein autonomer Echtgeld-Trading-Bot.

## Unverhandelbare Regeln

1. Keine Live-Order-Funktion implementieren, solange keine ausdrücklich getrennte
   Paper-Trading-Phase, Risiko-Spezifikation und manuelle Freigabe existiert.
2. Niemals zukünftige Daten für Signale oder Ausführungen verwenden.
3. Jede neue Strategie benötigt mindestens:
   - einen Test gegen Look-ahead-Bias,
   - einen Test für Gebühren,
   - einen Test auf gültige Positionswerte,
   - dokumentierte Parameter.
4. Handelskosten dürfen nicht stillschweigend deaktiviert werden.
5. Keine Kennzahl als Gewinngarantie darstellen.
6. Bei Änderungen stets `pytest -q` ausführen.
7. Fehler nicht verstecken; Datenlücken, ungültige Kurse und leere Ergebnisse
   müssen verständliche Fehlermeldungen erzeugen.

## Nächster Ausbauauftrag

Implementiere in kleinen, überprüfbaren Schritten:

1. Walk-forward-Optimierung:
   - rollierende Train-/Test-Fenster,
   - Parameterwahl nur im Trainingsfenster,
   - lückenlose Out-of-sample-Equity,
   - Export der gewählten Parameter pro Fenster.
2. Parameter-Robustheit:
   - Grid Search,
   - Heatmap für Rendite, Sharpe und Drawdown,
   - Kennzeichnung instabiler Einzelspitzen.
3. Monte-Carlo:
   - zufällige Neuordnung abgeschlossener Trades,
   - Verteilung von Endkapital und Max Drawdown,
   - konfigurierbarer Seed für Reproduzierbarkeit.
4. Risikoanalyse:
   - Value at Risk und Expected Shortfall als Zusatzkennzahlen,
   - getrennte Long-/Short-Ergebnisse,
   - Kostenanteil am Bruttogewinn.
5. Tests und Dokumentation aktualisieren.

## Definition of Done

- `pytest -q` ist grün.
- Keine Look-ahead-Verletzung.
- Neue Funktionen sind im Dashboard und in der CLI erreichbar.
- Exporte sind maschinenlesbar.
- README enthält ein reproduzierbares Beispiel.
