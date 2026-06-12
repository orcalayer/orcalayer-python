# Changelog

## 0.1.0 — 2026-06-12

Initial release.

- `OrcaLayer` client with anonymous and Premium (Bearer key) access tiers.
- Methods: `leaderboard`, `wallet_overview`, `wallet_positions`, `markets`, `whale_alerts` (Premium).
- Automatic retry on HTTP 429 (honours `Retry-After`, exponential backoff) and single retry on 502.
- Typed exceptions: `PremiumRequiredError`, `AuthenticationError`, `RateLimitError`, `ServerError`.
