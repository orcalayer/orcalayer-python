"""Offline tests for retry semantics (202 / 429 / 502) via httpx.MockTransport."""

import httpx
import pytest

from orcalayer import (
    APIError,
    AuthenticationError,
    OrcaLayer,
    RateLimitError,
    WalletComputingError,
)


def make_client(responses: list[httpx.Response]) -> OrcaLayer:
    """OrcaLayer whose HTTP layer replays canned responses in order."""
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return queue.pop(0)

    ol = OrcaLayer()
    ol._client = httpx.Client(transport=httpx.MockTransport(handler))
    return ol


def test_202_retries_once_then_returns_data():
    ol = make_client([
        httpx.Response(202, headers={"Retry-After": "1"}, json={"detail": "computing"}),
        httpx.Response(200, json={"wallet": "0xabc", "total_pnl": 1.0}),
    ])
    data = ol.wallet_overview("0xabc")
    assert data["total_pnl"] == 1.0


def test_202_twice_raises_computing_error():
    ol = make_client([
        httpx.Response(202, headers={"Retry-After": "1"}, json={"detail": "computing"}),
        httpx.Response(202, headers={"Retry-After": "30"}, json={"detail": "computing"}),
    ])
    with pytest.raises(WalletComputingError) as exc:
        ol.wallet_overview("0xabc")
    assert exc.value.retry_after == 30


def test_429_long_retry_after_raises_immediately():
    # Retry-After beyond 300s = daily quota; must not sleep/retry.
    ol = make_client([
        httpx.Response(429, headers={"Retry-After": "3600"}, json={"error": "daily"}),
    ])
    with pytest.raises(RateLimitError) as exc:
        ol.wallet_overview("0xabc")
    assert exc.value.retry_after == 3600


def test_429_short_then_ok_retries():
    ol = make_client([
        httpx.Response(429, headers={"Retry-After": "1"}, json={"error": "burst"}),
        httpx.Response(200, json={"ok": True}),
    ])
    assert ol.wallet_overview("0xabc") == {"ok": True}


def test_502_single_retry():
    ol = make_client([
        httpx.Response(502, text="bad gateway"),
        httpx.Response(200, json={"ok": True}),
    ])
    assert ol.markets(limit=1) == {"ok": True}


def test_429_then_502_then_ok():
    # The 502 retry budget is independent of the 429 budget.
    ol = make_client([
        httpx.Response(429, headers={"Retry-After": "1"}, json={"error": "burst"}),
        httpx.Response(502, text="bad gateway"),
        httpx.Response(200, json={"ok": True}),
    ])
    assert ol.markets(limit=1) == {"ok": True}


def test_unhandled_4xx_raises_api_error():
    ol = make_client([
        httpx.Response(404, json={"detail": "no such market"}),
    ])
    with pytest.raises(APIError) as exc:
        ol.markets(limit=1)
    assert exc.value.status_code == 404
    assert "no such market" in exc.value.body


def test_invalid_json_on_200_raises_api_error():
    ol = make_client([
        httpx.Response(200, text="<html>not json</html>"),
    ])
    with pytest.raises(APIError) as exc:
        ol.markets(limit=1)
    assert "not valid JSON" in str(exc.value)


def test_401_on_public_endpoint_mentions_anonymous():
    ol = make_client([
        httpx.Response(401, json={"error": "Invalid API key"}),
    ])
    with pytest.raises(AuthenticationError) as exc:
        ol.markets(limit=1)
    assert "without an API key" in str(exc.value)


def test_key_rejected_on_public_falls_back_to_anonymous():
    # A bad key 403s the Premium surface; the client retries once anonymously
    # on /api/v2 (no auth header) and returns the public data.
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("Authorization")))
        if len(seen) == 1:
            return httpx.Response(403, json={"error": "not premium"})
        return httpx.Response(200, json={"ok": True})

    ol = OrcaLayer(api_key="bad-key")
    ol._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer bad-key"},
    )
    assert ol.markets(limit=1) == {"ok": True}
    assert len(seen) == 2
    assert "/api/public/v1/" in seen[0][0] and seen[0][1] == "Bearer bad-key"
    assert "/api/v2/" in seen[1][0] and seen[1][1] is None


def test_premium_endpoint_403_does_not_fall_back():
    ol = make_client([httpx.Response(403, json={"error": "no premium plan"})])
    ol.api_key = "somekey"  # a keyed client hitting a Premium-only endpoint
    with pytest.raises(AuthenticationError) as exc:
        ol.whale_alerts(minutes=5)
    assert exc.value.status_code == 403


def test_retry_after_accepts_http_date():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    from orcalayer.client import _retry_after_seconds

    when = datetime.now(timezone.utc) + timedelta(seconds=30)
    resp = httpx.Response(429, headers={"Retry-After": format_datetime(when)})
    assert 20 <= _retry_after_seconds(resp) <= 31


def test_max_total_seconds_stops_retrying():
    # A retry that would sleep past the budget raises instead of blocking.
    ol = make_client([httpx.Response(429, headers={"Retry-After": "10"}, json={"error": "burst"})])
    ol.max_total_seconds = 1.0
    with pytest.raises(RateLimitError) as exc:
        ol.markets(limit=1)
    assert exc.value.retry_after == 10
