# Changelog

## 0.1.1 — 2026-06-13

- HTTP 202 contract for cold heavy wallets: one automatic retry after
  `Retry-After`, then `WalletComputingError` — a 202 body is never returned
  as wallet data. (Shipped in the repo after 0.1.0; first time on PyPI.)
- `RateLimitError` is raised immediately (no retries) when `Retry-After`
  exceeds 5 minutes — that signals the anonymous daily cap, not a burst.
- 502 retry budget is now independent of the 429 retry budget.
- New `APIError` for unhandled 4xx responses (404/400/422) and non-JSON
  bodies; carries `status_code` and `body`.
- `AuthenticationError` on public endpoints now notes that anonymous access
  is available.
- Type hints shipped (`py.typed`).
- `User-Agent` is now `orcalayer-python/<version>`.
- Tests: `pytest` runs offline tests only; live smoke tests are behind the
  `live` marker (`pytest -m live`).

## 0.1.0 — 2026-06-12

Initial release.

- `OrcaLayer` client with anonymous and Premium (Bearer key) access tiers.
- Methods: `leaderboard`, `wallet_overview`, `wallet_positions`, `markets`, `whale_alerts` (Premium).
- Automatic retry on HTTP 429 (honours `Retry-After`, exponential backoff) and single retry on 502.
- Typed exceptions: `PremiumRequiredError`, `AuthenticationError`, `RateLimitError`, `ServerError`.
