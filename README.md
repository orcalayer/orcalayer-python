# orcalayer

Official Python client for the [OrcaLayer API](https://orcalayer.com) — Polymarket whale and market analytics: wallet P&L, open positions, smart-whale leaderboard, market search and real-time whale alerts.

## Install

```
pip install orcalayer
```

Requires Python 3.10+. Single dependency: `httpx`.

## Quickstart

Three lines to a first result — no API key needed for public endpoints:

```python
from orcalayer import OrcaLayer

ol = OrcaLayer()
print(ol.leaderboard(limit=5))
```

With a Premium API key ([get one here](https://orcalayer.com/pricing)) you get a higher rate limit (600 req/min vs 200/min anonymous) and access to Premium endpoints such as whale alerts:

```python
ol = OrcaLayer(api_key="ol_your_key")
alerts = ol.whale_alerts(minutes=30, min_usd=1000)
```

## Methods

| Method | Endpoint | Access |
|---|---|---|
| `leaderboard(sort, category, limit, ...)` | Smart-whale leaderboard with server-side filters | Public |
| `wallet_overview(address)` | Wallet profile + trading stats (accepts 0x address or nickname) | Public |
| `wallet_positions(address, limit, offset)` | Open positions, sorted by current value | Public |
| `markets(q, category, min_volume, ...)` | Market search (accepts free text or a Polymarket URL) | Public |
| `whale_alerts(minutes, min_usd, ...)` | Recent smart-whale trades feed | Premium |

All methods return the JSON response as a plain `dict`, exactly as the API sends it. Full field reference: [orcalayer.com/docs](https://orcalayer.com/docs).

## Behavior notes

- **Rate limits**: on HTTP 429 the client reads `Retry-After` and retries with exponential backoff (default 3 attempts). Disable with `OrcaLayer(retry_on_rate_limit=False)`.
- **Transient 502** responses are retried once automatically.
- **Premium endpoints without a key** raise `PremiumRequiredError` with a link to [pricing](https://orcalayer.com/pricing) — no network call is made.
- **Wallet overview freshness**: responses include `as_of` (data timestamp) and `degraded` (heavy side-stats timed out, core stats still present).
- **Cold heavy wallets** answer HTTP 202 while their stats are computed server-side. The client retries once automatically after the server's `Retry-After` interval; if the wallet is still not ready it raises `WalletComputingError` (carrying `retry_after`) so a 202 body is never mistaken for wallet data.

## Errors

```python
from orcalayer import PremiumRequiredError, RateLimitError, AuthenticationError, ServerError
```

All inherit from `orcalayer.OrcaLayerError`.

## License

MIT. See [LICENSE](LICENSE).

Data is provided for informational purposes only and is not financial advice.
