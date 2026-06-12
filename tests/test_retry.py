"""Offline tests for retry semantics (202 / 429 / 502) via httpx.MockTransport."""

import httpx
import pytest

from orcalayer import OrcaLayer, RateLimitError, WalletComputingError


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
