"""Find the top smart-money whales in a category.

Uses the public leaderboard endpoint — no API key required, runs as-is.

    python find_top_whales.py            # top whales overall
    python find_top_whales.py Crypto     # top whales in a category
"""

import sys

from orcalayer import OrcaLayer


def main() -> None:
    category = sys.argv[1] if len(sys.argv) > 1 else None

    ol = OrcaLayer()  # anonymous — public endpoint
    data = ol.leaderboard(
        sort="pnl",
        category=category,
        filter="smart",
        limit=10,
        min_markets=10,   # ignore wallets with too few resolved markets
    )

    whales = data.get("whales", [])
    label = f" in {category}" if category else ""
    print(f"Top {len(whales)} smart whales{label} by P&L:\n")
    for i, w in enumerate(whales, 1):
        name = w.get("name") or w.get("wallet", "")[:12]
        print(
            f"{i:>2}. {name:<24} "
            f"P&L ${w.get('total_pnl', 0):>14,.0f} | "
            f"win rate {w.get('win_rate', 0):>5.1f}% | "
            f"markets {w.get('resolved_markets', 0)}"
        )


if __name__ == "__main__":
    main()
