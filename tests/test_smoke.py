"""Smoke tests against the live API.

Anonymous tests always run. Premium tests need ORCALAYER_TEST_API_KEY in the
environment and are skipped otherwise. Run: python -m pytest tests/ -v
"""

import os

import pytest

from orcalayer import OrcaLayer, PremiumRequiredError

PREMIUM_KEY = os.environ.get("ORCALAYER_TEST_API_KEY", "")
# Known active wallet for read-only smoke checks (public leaderboard member).
TEST_WALLET = os.environ.get("ORCALAYER_TEST_WALLET", "")


@pytest.fixture(scope="module")
def anon():
    with OrcaLayer() as client:
        yield client


def test_leaderboard_anon(anon):
    data = anon.leaderboard(limit=5)
    assert isinstance(data, dict)
    whales = data.get("whales") or data.get("leaderboard") or data.get("results")
    assert whales, f"unexpected leaderboard shape: {list(data)}"
    assert len(whales) <= 5


def test_markets_anon(anon):
    data = anon.markets(limit=5)
    assert isinstance(data, dict)
    assert data.get("markets") or data.get("results"), f"unexpected shape: {list(data)}"


def test_wallet_overview_anon(anon):
    address = TEST_WALLET or _first_leaderboard_wallet(anon)
    data = anon.wallet_overview(address)
    assert isinstance(data, dict)
    assert "error" not in data, data.get("error")


def test_wallet_positions_anon(anon):
    address = TEST_WALLET or _first_leaderboard_wallet(anon)
    data = anon.wallet_positions(address, limit=10)
    assert isinstance(data, dict)


def test_premium_without_key_raises(anon):
    with pytest.raises(PremiumRequiredError) as exc:
        anon.whale_alerts()
    assert "pricing" in str(exc.value)


@pytest.mark.skipif(not PREMIUM_KEY, reason="ORCALAYER_TEST_API_KEY not set")
def test_whale_alerts_premium():
    with OrcaLayer(api_key=PREMIUM_KEY) as client:
        data = client.whale_alerts(minutes=60, limit=5)
    assert isinstance(data, dict)
    assert "error" not in data, data.get("error")


@pytest.mark.skipif(not PREMIUM_KEY, reason="ORCALAYER_TEST_API_KEY not set")
def test_overview_via_premium_surface():
    with OrcaLayer(api_key=PREMIUM_KEY) as client:
        address = TEST_WALLET or _first_leaderboard_wallet(client)
        data = client.wallet_overview(address)
    assert isinstance(data, dict)
    assert "error" not in data, data.get("error")


def _first_leaderboard_wallet(client):
    data = client.leaderboard(limit=1)
    whales = data.get("whales") or data.get("leaderboard") or data.get("results")
    entry = whales[0]
    return entry.get("wallet") or entry.get("address") or entry.get("proxy_wallet")
