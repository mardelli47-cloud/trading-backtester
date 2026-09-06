# MEME RADAR – Solana On-Chain Risk & Token Intelligence

Ein **read-only** Analysewerkzeug für SPL- und Token-2022-Mints. MEME RADAR liest
echte On-chain- und Marktdaten, erklärt heuristische Risikobefunde und zeigt die
Datenabdeckung. Es ist keine Finanzberatung und kann keine Sicherheit garantieren.

## Schnellstart

Voraussetzung: Node.js 20.9 oder neuer.

```bash
npm install
npm run dev
```

Öffne [http://localhost:3000](http://localhost:3000), füge eine Solana
Mint-Adresse ein und wähle **Token analysieren**. Keine Wallet ist erforderlich.

## Environment

Kopiere bei Bedarf `.env.example` nach `.env.local`.

| Variable | Pflicht | Wofür | Ohne Variable |
|---|---|---|---|
| `SOLANA_RPC_URL` | nein | Stabiler eigener Mainnet-RPC | Öffentlicher Solana-RPC best-effort; Rate Limits möglich |
| `HELIUS_API_KEY` | nein | Künftige erweiterte Historie/Creator-Evidenz, nur serverseitig | Creator-Historie als nicht konfiguriert/unbekannt |
| `ENABLE_DEMO_MODE` | nein | Reserviert für explizit markierte lokale Fixtures | Ausschließlich Live-Daten oder `Nicht verfügbar` |

Keine echten Schlüssel in `.env.example` oder Git speichern.

## Was bedeuten Score und Data Coverage?

Der Risk Score ist eine reproduzierbare, gewichtete **Heuristik**. Grün heißt nur,
dass der konkrete Check unauffällig war. Unter 60 % Coverage verweigert die UI eine
zuverlässige Gesamtbewertung: Fehlende Daten sind nicht automatisch sicher.
Alle Gewichte stehen auf `/methodology` und in `risk-config.ts`.

## Warum sind manche Daten nicht verfügbar?

RPCs und Drittanbieter können ausfallen oder Rate Limits anwenden. Manche Tokens
haben keinen DexScreener-Pool. Creator und LP-Lock bleiben unbekannt, wenn keine
belastbare Evidenz vorliegt. Die On-chain-Analyse bleibt bei einem Marktfehler nutzbar.

## Was kann dieser Scanner nicht erkennen?

- Ein niedriger Score garantiert weder Sicherheit noch Kursentwicklung.
- Neue Angriffsmethoden sowie komplexe Transfer-Hook-Logik können unbekannt sein.
- Wallets können wirtschaftlich zusammengehören, ohne klar verknüpft zu sein.
- Creator-Inferenz, LP-Locks und Wallet-Klassifikation sind nicht immer eindeutig.
- Markt- und Providerdaten können verzögert oder zeitweise ausgefallen sein.

## Tests, Prüfung und Production

```bash
npm test                 # stabile Unit Tests mit Fixtures
npm run test:e2e         # Browser-Kernflüsse (installiert ggf. Playwright-Browser)
npm run test:integration # optionaler, variabler Mainnet-RPC-Test
npm run verify           # lint + typecheck + Unit Tests + Production Build
npm run build && npm start
pytest -q                # bestehender Backtester, gemäß Repository-Regel
```

Für Deployment (z. B. Vercel/Node-Host) Repository importieren, `npm run build`
verwenden und optionale Environment-Variablen serverseitig setzen. Architektur und
Datenherkunft stehen in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
