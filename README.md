# orcalayer

[![CI](https://github.com/orcalayer/orcalayer-python/actions/workflows/ci.yml/badge.svg)](https://github.com/orcalayer/orcalayer-python/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/orcalayer)](https://pypi.org/project/orcalayer/)

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

Anonymous access is limited to 200 requests/min per IP, and wallet endpoints (`wallet_overview`, `wallet_positions`) additionally to 300 requests/day per IP. With a Premium API key ([get one here](https://orcalayer.com/pricing)) you get 600 req/min, no daily cap, and access to Premium endpoints such as whale alerts:

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

- **Rate limits**: on HTTP 429 the client reads `Retry-After` and retries with exponential backoff (default 3 attempts). Disable with `OrcaLayer(retry_on_rate_limit=False)`. A `Retry-After` beyond 5 minutes signals the anonymous daily cap rather than a burst — the client then raises `RateLimitError` immediately instead of retrying.
- **Transient 502** responses are retried once automatically.
- **Premium endpoints without a key** raise `PremiumRequiredError` with a link to [pricing](https://orcalayer.com/pricing) — no network call is made.
- **Wallet overview freshness**: responses include `as_of` (data timestamp) and `degraded` (heavy side-stats timed out, core stats still present).
- **Cold heavy wallets** answer HTTP 202 while their stats are computed server-side. The client retries once automatically after the server's `Retry-After` interval; if the wallet is still not ready it raises `WalletComputingError` (carrying `retry_after`) so a 202 body is never mistaken for wallet data.

## Errors

All exceptions inherit from `orcalayer.OrcaLayerError`, so one `except` catches everything:

```python
from orcalayer import OrcaLayer, OrcaLayerError, RateLimitError

ol = OrcaLayer()
try:
    data = ol.wallet_overview("0x...")
except RateLimitError as e:
    print(f"rate limited, retry in {e.retry_after:.0f}s")
except OrcaLayerError as e:
    print(f"request failed: {e}")
```

| Exception | Raised on |
|---|---|
| `PremiumRequiredError` | Premium endpoint called without a key (no network call made) |
| `AuthenticationError` | Key rejected (HTTP 401/403) |
| `RateLimitError` | HTTP 429 after retries, or immediately for the daily cap; carries `retry_after` |
| `WalletComputingError` | Heavy wallet still computing (HTTP 202 twice); carries `retry_after` |
| `APIError` | Unhandled 4xx (404/400/422) or a non-JSON body; carries `status_code` and `body` |
| `ServerError` | Unexpected 5xx |

The package ships type hints (`py.typed`).

## License

MIT. See [LICENSE](LICENSE).

Data is provided for informational purposes only and is not financial advice.
