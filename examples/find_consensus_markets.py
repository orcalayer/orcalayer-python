"""Find markets where smart whales are clustering.

Searches markets with server-side filters — no API key required. Shows the
YES price and how many whales sit on each side, so you can spot one-sided
smart-money positioning.

    python find_consensus_markets.py                 # high-volume markets
    python find_consensus_markets.py Trump           # text search
    python find_consensus_markets.py "" Politics     # by category
"""

import sys

from orcalayer import OrcaLayer


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    category = sys.argv[2] if len(sys.argv) > 2 else None

    ol = OrcaLayer()  # anonymous — public endpoint
    data = ol.markets(
        query,
        category=category,
        limit=10,
        min_volume=100_000,   # USD — skip thin markets
        min_whales=5,         # at least 5 smart whales present
    )

    markets = data.get("markets", [])
    print(f"{len(markets)} market(s) with whale activity:\n")
    for m in markets:
        yes = m.get("whales_yes", 0)
        no = m.get("whales_no", 0)
        print(f"- {m.get('question', '?')[:60]}")
        print(
            f"    YES price {m.get('price_yes', 0):.2f} | "
            f"whales YES {yes} / NO {no} | "
            f"volume ${m.get('volume', 0):,.0f}"
        )


if __name__ == "__main__":
    main()
