# Changelog

## 0.2.1 — 2026-07-02

- Public fallback is now sticky per client: after a key is rejected once on a
  public endpoint, later public calls skip auth and go straight to `/api/v2`,
  so a bad key no longer costs a doubled round-trip on every public call.
  Premium-only endpoints still send the key.
- Docs: example API keys use the real `sk_orca_` prefix.

## 0.2.0 — 2026-07-02

- Public fallback for rejected keys: when a bad, expired or non-Premium
  `api_key` is rejected (HTTP 401/403) on a **public** endpoint, the client now
  retries the call once anonymously against `/api/v2` and logs a one-time
  warning, instead of failing a call that works without a key. Premium-only
  endpoints (`whale_alerts`) still raise `AuthenticationError` at once.
- New `max_total_seconds` constructor option: an overall wall-clock budget
  across all retries for a single call. A retry that would sleep past the
  budget raises the pending typed error instead of blocking (worst-case
  202+429+502 chains could previously stall for minutes).
- `Retry-After` now also accepts an HTTP-date (RFC 9110), not just a number of
  seconds.
- `wallet_positions` docstring corrected: the API returns the full open-position
  set in one response and ignores `limit`/`offset` and ordering — page/sort
  client-side.

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
