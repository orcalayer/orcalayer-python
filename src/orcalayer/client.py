"""OrcaLayer API client.

Two access tiers, selected automatically by whether an API key is given:

* Anonymous  — public endpoints under ``/api/v2`` (200 requests/min per IP).
* Premium    — same data plus Premium endpoints under ``/api/public/v1``
               with ``Authorization: Bearer`` auth (600 requests/min per key).

All methods return the JSON response as a plain ``dict`` — exactly what the
API sends, no client-side reshaping.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .errors import (
    AuthenticationError,
    OrcaLayerError,
    PremiumRequiredError,
    RateLimitError,
    ServerError,
    WalletComputingError,
)

DEFAULT_BASE_URL = "https://orcalayer.com"
PUBLIC_PREFIX = "/api/v2"
PREMIUM_PREFIX = "/api/public/v1"
USER_AGENT = "Mozilla/5.0 (compatible; orcalayer-python/0.1.0)"


class OrcaLayer:
    """Client for the OrcaLayer API.

    Args:
        api_key: Premium API key. Omit for anonymous access to public
            endpoints; Premium endpoints then raise ``PremiumRequiredError``.
        base_url: API host. Defaults to ``https://orcalayer.com``.
        timeout: Per-request timeout in seconds.
        retry_on_rate_limit: When True (default), HTTP 429 responses are
            retried using the server's ``Retry-After`` header with
            exponential backoff. Set False to raise ``RateLimitError``
            immediately.
        max_retries: Maximum retry attempts for 429 responses.

    Example:
        >>> from orcalayer import OrcaLayer
        >>> ol = OrcaLayer()
        >>> top = ol.leaderboard(limit=10)
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        retry_on_rate_limit: bool = True,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.retry_on_rate_limit = retry_on_rate_limit
        self.max_retries = max_retries
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(timeout=timeout, headers=headers)

    # ── HTTP core ────────────────────────────────────────────────────────

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        premium_only: bool = False,
    ) -> dict:
        """GET ``path`` (no leading slash) and return the parsed JSON dict.

        With an API key every call is routed through the Premium surface
        (``/api/public/v1``, Bearer auth, higher rate limit). Without a key,
        public endpoints go to ``/api/v2`` and Premium-only endpoints raise
        ``PremiumRequiredError``.
        """
        if premium_only and not self.api_key:
            raise PremiumRequiredError(path)
        prefix = PREMIUM_PREFIX if self.api_key else PUBLIC_PREFIX
        url = f"{self.base_url}{prefix}/{path}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}

        attempt = 0
        retried_202 = False
        while True:
            try:
                resp = self._client.get(url, params=clean)
            except httpx.HTTPError as exc:
                raise OrcaLayerError(f"Request to {url} failed: {exc}") from exc

            if resp.status_code == 202:
                # Cold heavy wallet: stats are being computed server-side.
                # One automatic retry after Retry-After, then a typed error
                # so callers never mistake the 202 body for real data.
                retry_after = _retry_after_seconds(resp)
                if retried_202:
                    raise WalletComputingError(retry_after)
                retried_202 = True
                time.sleep(min(retry_after, 60))
                continue

            if resp.status_code == 429:
                retry_after = _retry_after_seconds(resp)
                # A Retry-After beyond 5 minutes signals a daily quota, not a
                # sliding-window burst — retrying within this process is futile.
                if (
                    not self.retry_on_rate_limit
                    or attempt >= self.max_retries
                    or retry_after > 300
                ):
                    raise RateLimitError(retry_after, _detail(resp))
                # Server window is sliding 60s; honour Retry-After and add
                # exponential backoff across attempts so bursts drain cleanly.
                time.sleep(min(max(retry_after, 2.0 ** attempt), 120.0))
                attempt += 1
                continue

            if resp.status_code == 502 and attempt == 0:
                # Transient gateway hiccup: a single retry, then give up.
                attempt += 1
                time.sleep(1)
                continue

            if resp.status_code in (401, 403):
                raise AuthenticationError(resp.status_code, _detail(resp))

            if resp.status_code >= 500:
                raise ServerError(resp.status_code, resp.text)

            resp.raise_for_status()
            return resp.json()

    # ── Public endpoints (work with or without a key) ────────────────────

    def leaderboard(
        self,
        *,
        sort: str = "pnl",
        category: str | None = None,
        filter: str = "smart",
        limit: int = 50,
        offset: int = 0,
        min_markets: int | None = None,
        min_wr: float | None = None,
        min_pnl: float | None = None,
        min_profit_factor: float | None = None,
        max_avg_entry: float | None = None,
        max_sports_pct: float | None = None,
    ) -> dict:
        """Smart-whale leaderboard.

        Args:
            sort: ``pnl`` (default), ``win_rate``, ``volume`` or ``trades``.
            category: Market category filter (e.g. ``Crypto``, ``Sports``).
            filter: ``smart`` (curated whales, default) or ``all``.
            limit / offset: Pagination.
            min_markets, min_wr, min_pnl, min_profit_factor, max_avg_entry,
            max_sports_pct: Optional numeric screens, applied server-side.
        """
        return self._get(
            "whales/leaderboard",
            {
                "sort": sort,
                "category": category,
                "filter": filter,
                "limit": limit,
                "offset": offset,
                "min_markets": min_markets,
                "min_wr": min_wr,
                "min_pnl": min_pnl,
                "min_profit_factor": min_profit_factor,
                "max_avg_entry": max_avg_entry,
                "max_sports_pct": max_sports_pct,
            },
        )

    def wallet_overview(self, address: str) -> dict:
        """Wallet profile and trading stats.

        ``address`` is a 0x wallet address or an OrcaLayer nickname.
        The response carries ``as_of`` (data timestamp, epoch seconds) and
        ``degraded`` (True when heavy side-stats timed out; core stats are
        still present). A cold heavy wallet answers HTTP 202 while its stats
        are computed: the client retries once automatically after the
        server's ``Retry-After`` interval and raises ``WalletComputingError``
        if the wallet is still not ready.
        """
        return self._get(f"wallet/{address}/overview")

    def wallet_positions(self, address: str, *, limit: int = 200, offset: int = 0) -> dict:
        """Open positions for a wallet (sorted by current value, cap 500/page)."""
        return self._get(
            f"wallet/{address}/positions", {"limit": limit, "offset": offset}
        )

    def markets(
        self,
        q: str = "",
        *,
        category: str | None = None,
        limit: int = 50,
        offset: int = 0,
        min_volume: float | None = None,
        min_whales: int | None = None,
        price_min: int | None = None,
        price_max: int | None = None,
    ) -> dict:
        """Search or browse markets.

        Args:
            q: Free-text query; also accepts a Polymarket URL or slug.
            category: ``Crypto`` | ``Geopolitics`` | ``Sports`` | ``Politics``
                | ``Economics`` | ``Tech/AI``.
            min_volume: Minimum market volume in USD.
            min_whales: Minimum count of smart whales in the market.
            price_min / price_max: YES price band in cents (0-100).
        """
        return self._get(
            "markets/search",
            {
                "q": q,
                "category": category,
                "limit": limit,
                "offset": offset,
                "min_volume": min_volume,
                "min_whales": min_whales,
                "price_min": price_min,
                "price_max": price_max,
            },
        )

    # ── Premium endpoints (API key required) ─────────────────────────────

    def whale_alerts(
        self,
        *,
        minutes: int = 10,
        wallet: str | None = None,
        market_id: str | None = None,
        min_usd: float = 10,
        smart_only: bool = True,
        limit: int = 50,
        category: str | None = None,
    ) -> dict:
        """Recent smart-whale trades (Premium).

        Args:
            minutes: Lookback window, max 1440 (24h).
            wallet: Filter to one wallet address.
            market_id: Filter to one market.
            min_usd: Minimum trade size in USD.
            smart_only: Only curated smart whales (default True).
        """
        return self._get(
            "whale-alerts",
            {
                "minutes": minutes,
                "wallet": wallet,
                "market_id": market_id,
                "min_usd": min_usd,
                "smart_only": smart_only,
                "limit": limit,
                "category": category,
            },
            premium_only=True,
        )

    # ── Lifecycle ────────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "OrcaLayer":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _retry_after_seconds(resp: httpx.Response) -> float:
    try:
        return max(1.0, float(resp.headers.get("Retry-After", "60")))
    except ValueError:
        return 60.0


def _detail(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error", ""))
    except Exception:
        return ""
