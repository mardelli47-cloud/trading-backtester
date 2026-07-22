# Auftrag an Codex

Arbeite im vorhandenen Repository und entwickle den Backtester zu einer belastbaren
Research-Anwendung weiter. Lies zuerst `README.md` und `AGENTS.md`.

## Aufgabe

Implementiere eine Walk-forward-Analyse mit echter Out-of-sample-Auswertung.

### Anforderungen

- Unterstütze alle drei vorhandenen Strategien.
- Der Nutzer definiert:
  - Trainingsfenster in Balken,
  - Testfenster in Balken,
  - Schrittweite,
  - Parameter-Grid,
  - Optimierungsziel: Sharpe, Gesamtrendite oder kleinster Drawdown.
- Optimiere Parameter ausschließlich auf dem jeweiligen Trainingsfenster.
- Wende die besten Parameter danach unverändert auf das direkt folgende
  Testfenster an.
- Füge die Testfenster zu einer lückenlosen Out-of-sample-Equity-Kurve zusammen.
- Verhindere Datenüberschneidungen und Look-ahead-Bias.
- Speichere pro Fenster:
  - Zeitraum,
  - gewählte Parameter,
  - Trainingskennzahl,
  - Testkennzahlen,
  - Anzahl Trades.
- Ergänze das Streamlit-Dashboard um einen eigenen Bereich „Walk-forward“.
- Ergänze die CLI um passende Argumente und CSV-/JSON-Exporte.
- Nutze Multiprocessing nur optional; deterministisches Verhalten ist wichtiger.
- Füge Tests für Fenstergrenzen, Parameterwahl und Look-ahead-Schutz hinzu.
- Aktualisiere README und AGENTS.md.
- Führe `pytest -q` aus und behebe alle Fehler.

## Arbeitsweise

1. Analysiere zuerst den vorhandenen Code und nenne kurz die betroffenen Dateien.
2. Implementiere kleine, klar abgegrenzte Änderungen.
3. Verändere keine bestehenden Ergebnisse ohne Begründung.
4. Zeige am Ende:
   - Zusammenfassung,
   - ausgeführte Tests,
   - verbleibende Grenzen,
   - genaue Startbefehle für Dashboard und CLI.

Erstelle keine Echtgeld-Order-Funktion.
