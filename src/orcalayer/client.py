"""OrcaLayer API client.

Two access tiers, selected automatically by whether an API key is given:

* Anonymous  — public endpoints under ``/api/v2`` (200 requests/min per IP).
* Premium    — same data plus Premium endpoints under ``/api/public/v1``
               with ``Authorization: Bearer`` auth (600 requests/min per key).

All methods return the JSON response as a plain ``dict`` — exactly what the
API sends, no client-side reshaping.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from ._version import __version__
from .errors import (
    APIError,
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
USER_AGENT = f"orcalayer-python/{__version__}"


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
        max_total_seconds: Optional overall wall-clock budget across all retries
            for a single call. When a retry would sleep past this budget the
            pending typed error (``WalletComputingError`` / ``RateLimitError`` /
            ``ServerError``) is raised instead of blocking. ``None`` (default) =
            no overall cap (each request is still bounded by ``timeout``).
        user_agent_suffix: Optional token appended to the ``User-Agent``
            header (e.g. ``orcalayer-mcp/0.1.1``) so server-side logs can
            attribute traffic to a specific frontend. Omit for plain SDK use.

    A bad or non-Premium ``api_key`` no longer breaks public calls: if a key is
    rejected (401/403) on a non-Premium-only endpoint, the client retries once
    anonymously against the public surface and logs a one-time warning.

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
        max_total_seconds: float | None = None,
        user_agent_suffix: str | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.retry_on_rate_limit = retry_on_rate_limit
        self.max_retries = max_retries
        self.max_total_seconds = max_total_seconds
        self._warned_public_fallback = False
        self._public_fallback_sticky = False
        user_agent = (
            f"{USER_AGENT} {user_agent_suffix}" if user_agent_suffix else USER_AGENT
        )
        headers = {"User-Agent": user_agent, "Accept": "application/json"}
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
        poll: bool = True,
    ) -> dict:
        """GET ``path`` (no leading slash) and return the parsed JSON dict.

        With an API key every call is routed through the Premium surface
        (``/api/public/v1``, Bearer auth, higher rate limit). Without a key,
        public endpoints go to ``/api/v2`` and Premium-only endpoints raise
        ``PremiumRequiredError``.

        If a key is rejected (HTTP 401/403) on a **non**-Premium-only endpoint,
        the client retries the call once anonymously against the public
        ``/api/v2`` surface (lower rate limits) and logs a one-time warning, so
        a bad or expired key never breaks a call that would work without one.
        Premium-only endpoints keep raising ``AuthenticationError`` at once.

        ``poll`` controls cold-wallet (HTTP 202) handling. When True (default)
        the client waits one ``Retry-After`` interval and retries once before
        raising ``WalletComputingError``. When False it raises immediately on
        the first 202 without sleeping — for callers (e.g. an MCP server) that
        must stay non-blocking and surface a "computing, retry later" notice.

        When ``max_total_seconds`` is set, a retry that would sleep past that
        overall budget raises the pending typed error instead of blocking.
        """
        if premium_only and not self.api_key:
            raise PremiumRequiredError(path)
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        deadline = (
            None if self.max_total_seconds is None
            else time.monotonic() + self.max_total_seconds
        )

        # Once a key has been rejected on a public endpoint, skip auth on later
        # public calls too, so a bad key does not cost a doubled round-trip every
        # time. Premium-only endpoints still send the key.
        use_auth = bool(self.api_key) and not (self._public_fallback_sticky and not premium_only)
        fell_back = False
        attempt = 0
        retried_202 = False
        retried_502 = False
        while True:
            prefix = PREMIUM_PREFIX if use_auth else PUBLIC_PREFIX
            url = f"{self.base_url}{prefix}/{path}"
            request = self._client.build_request("GET", url, params=clean)
            if not use_auth:
                # Anonymous call: drop the Bearer header the client carries.
                request.headers.pop("Authorization", None)
            try:
                resp = self._client.send(request)
            except httpx.HTTPError as exc:
                raise OrcaLayerError(f"Request to {url} failed: {exc}") from exc

            if resp.status_code == 202:
                # Cold heavy wallet: stats are being computed server-side.
                # With poll=True, one automatic retry after Retry-After, then a
                # typed error so callers never mistake the 202 body for real
                # data. With poll=False, raise at once without sleeping.
                retry_after = _retry_after_seconds(resp)
                if not poll or retried_202:
                    raise WalletComputingError(retry_after)
                retried_202 = True
                self._sleep_within(
                    min(retry_after, 60), deadline, WalletComputingError(retry_after)
                )
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
                self._sleep_within(
                    min(max(retry_after, 2.0 ** attempt), 120.0),
                    deadline,
                    RateLimitError(retry_after, _detail(resp)),
                )
                attempt += 1
                continue

            if resp.status_code == 502 and not retried_502:
                # Transient gateway hiccup: a single retry, independent of
                # the 429 retry budget (a 429->502 sequence gets both).
                retried_502 = True
                self._sleep_within(1, deadline, ServerError(502, resp.text))
                continue

            if resp.status_code in (401, 403):
                # A key rejected on a non-Premium-only endpoint: fall back to
                # anonymous public access once, rather than failing a call that
                # would have worked without a key at all.
                if not premium_only and use_auth and not fell_back:
                    fell_back = True
                    use_auth = False
                    self._public_fallback_sticky = True
                    self._warn_public_fallback(resp.status_code)
                    continue
                hint = (
                    "" if premium_only
                    else "Note: this endpoint also works without an API key "
                         "(anonymous access, lower limits)."
                )
                raise AuthenticationError(resp.status_code, _detail(resp), hint=hint)

            if resp.status_code >= 500:
                raise ServerError(resp.status_code, resp.text)

            if resp.status_code >= 400:
                # 404/400/422 and friends — typed, with the body preserved.
                raise APIError(resp.status_code, resp.text)

            try:
                return resp.json()
            except ValueError as exc:
                raise APIError(
                    resp.status_code, resp.text, note="Response body is not valid JSON."
                ) from exc

    def _sleep_within(
        self, seconds: float, deadline: float | None, on_timeout: OrcaLayerError
    ) -> None:
        """Sleep ``seconds`` unless it would pass the overall deadline — then
        raise the pending typed error instead of blocking past the budget."""
        if deadline is not None and time.monotonic() + seconds > deadline:
            raise on_timeout
        time.sleep(seconds)

    def _warn_public_fallback(self, status_code: int) -> None:
        """Warn once per client that a rejected key fell back to public access."""
        if self._warned_public_fallback:
            return
        self._warned_public_fallback = True
        logging.getLogger("orcalayer").warning(
            "API key rejected (HTTP %s) on the Premium surface; falling back to "
            "anonymous public access at lower rate limits. If you expect Premium "
            "access, check your key at https://orcalayer.com/settings.",
            status_code,
        )

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

    def wallet_overview(self, address: str, *, poll: bool = True) -> dict:
        """Wallet profile and trading stats.

        ``address`` is a 0x wallet address or an OrcaLayer nickname.
        The response carries ``as_of`` (data timestamp, epoch seconds) and
        ``degraded`` (True when heavy side-stats timed out; core stats are
        still present). A cold heavy wallet answers HTTP 202 while its stats
        are computed.

        ``poll`` (default True): wait one ``Retry-After`` interval and retry
        once, then raise ``WalletComputingError`` if still not ready. Set
        False to raise ``WalletComputingError`` immediately on the first 202
        without blocking — for non-blocking callers that surface a
        "computing, retry later" notice themselves.
        """
        return self._get(f"wallet/{address}/overview", poll=poll)

    def wallet_positions(self, address: str, *, limit: int = 200, offset: int = 0) -> dict:
        """Open positions for a wallet.

        Returns the wallet's full set of open positions in one response, under
        ``positions`` (with a ``count``). Note: the API currently **ignores**
        ``limit`` and ``offset`` and does **not** guarantee ordering — do any
        paging or sorting (e.g. by ``current_value``, descending) client-side.
        The parameters are accepted for forward compatibility.
        """
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
    raw = resp.headers.get("Retry-After", "60")
    try:
        return max(1.0, float(raw))
    except ValueError:
        pass
    # RFC 9110 also allows Retry-After as an HTTP-date; parse it to a delay.
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        dt = None
    if dt is not None:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(1.0, (dt - datetime.now(timezone.utc)).total_seconds())
    return 60.0


def _detail(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error", ""))
    except Exception:
        return ""
