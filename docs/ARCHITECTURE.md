# Architektur von MEME RADAR

```text
Responsive UI + TanStack Query
        ↓
GET /api/analyze/[mint]
        ↓
Provider Layer (parallel, fehlertolerant)
        ↓
Normalisierung und Zod-Validierung
        ↓
Transparente Risk Engine + Coverage
        ↓
TokenAnalysisResult / Watchlist-Snapshot
```

## Datenherkunft

- **Solana RPC:** Mint-Account, Programmzuordnung, Supply, Decimals, Authorities,
  Token-2022-Extensions und größte Token-Accounts. `SOLANA_RPC_URL` kann einen
  eigenen Endpunkt konfigurieren; der öffentliche Mainnet-Endpunkt ist nur ein
  Best-Effort-Fallback.
- **DexScreener:** Preis, Pools, Liquidität, FDV/Market Cap (getrennte Felder),
  Volumen, Transaktionen und Preisänderungen. Antworten werden validiert.
- **Enhanced History:** Die serverseitige Helius-Konfiguration ist vorbereitet.
  Ohne belastbare Historie bleibt Creator-Inferenz ausdrücklich unbekannt.

Unabhängige Provider laufen parallel. Der RPC ist für eine gültige Tokenanalyse
zwingend; ein Marktdatenfehler erzeugt dagegen ein partielles Resultat und senkt
die Coverage. Externe Metadaten werden nicht als HTML ausgeführt und URLs werden
nicht serverseitig aus Metadaten abgerufen.

## Sicherheit und Grenzen

Die Anwendung besitzt keine Wallet- oder Signierfunktion und führt keine Trades
aus. Explorer-URLs müssen zentral erzeugt werden. Geheimnisse bleiben in
serverseitigen Environment-Variablen. Alle Provider besitzen begrenzte Retries und
Timeouts. Ein niedriger Score ist keine Sicherheits- oder Gewinngarantie.
