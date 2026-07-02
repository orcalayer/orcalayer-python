"""Print recent smart-whale trades — a simple alerts feed.

This is a PREMIUM endpoint and requires an API key. Get one at
https://orcalayer.com/pricing and pass it via the ORCALAYER_API_KEY
environment variable (or edit API_KEY below — replace "sk_orca_..."):

    ORCALAYER_API_KEY=sk_orca_... python whale_alerts_feed.py

Run it WITHOUT a key and the client raises PremiumRequiredError before any
network call — this script catches it and points you to pricing.
"""

import os

from orcalayer import AuthenticationError, OrcaLayer, PremiumRequiredError

# Leave as None to demonstrate the no-key path; set ORCALAYER_API_KEY (or
# replace None with "sk_orca_...") to hit the live premium endpoint.
API_KEY = os.environ.get("ORCALAYER_API_KEY") or None


def main() -> None:
    ol = OrcaLayer(api_key=API_KEY)
    try:
        data = ol.whale_alerts(minutes=60, min_usd=1000, limit=15)
    except PremiumRequiredError as exc:
        print(exc)
        return
    except AuthenticationError as exc:
        print(exc)
        return

    alerts = data.get("alerts", [])
    print(f"{len(alerts)} smart-whale trade(s) in the last 60 min (min $1,000):\n")
    for a in alerts:
        whale = a.get("whale", {})
        trade = a.get("trade", {})
        market = a.get("market", {})
        name = whale.get("name") or whale.get("wallet", "")[:12]
        print(
            f"  {name:<20} {trade.get('action', '?'):<4} {trade.get('side', '?'):<3} "
            f"${trade.get('usd_amount', 0):>10,.0f} @ {trade.get('price', 0):.3f}  "
            f"{market.get('question', '?')[:45]}"
        )


if __name__ == "__main__":
    main()
