"""Show a wallet's profile, trading stats and current open positions.

Uses public endpoints — no API key required. Accepts a 0x address or an
OrcaLayer nickname.

    python track_wallet.py 0x55be7aa03ecfbe37aa5460db791205f7ac9ddca3
    python track_wallet.py coinman2
"""

import sys

from orcalayer import OrcaLayer


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python track_wallet.py <wallet-address-or-nickname>")
    address = sys.argv[1]

    ol = OrcaLayer()  # anonymous — public endpoints

    data = ol.wallet_overview(address)
    if data.get("error"):
        sys.exit(f"wallet not found: {data['error']}")

    profile = data.get("profile", {})
    overview = data.get("overview", {})
    stats = data.get("stats", {})

    print(f"Wallet: {profile.get('name') or address}")
    print(f"  markets traded : {overview.get('total_markets', 0):,}")
    print(f"  total trades   : {overview.get('total_trades', 0):,}")
    print(f"  total volume   : ${overview.get('total_volume', 0):,.0f}")
    print(f"  win rate       : {stats.get('win_rate', 0):.1f}%")
    print(f"  realized P&L   : ${stats.get('total_pnl', 0):,.0f}")
    if data.get("degraded"):
        print("  (some heavy stats timed out — overview is partial)")

    positions = ol.wallet_positions(address, limit=10)
    rows = positions.get("positions", [])
    print(f"\nOpen positions (showing up to {len(rows)}):")
    for p in rows:
        print(
            f"  {p.get('question', '?')[:50]:<50} "
            f"[{p.get('outcome', '?')}] "
            f"${p.get('current_value', 0):>10,.2f}  "
            f"P&L ${p.get('pnl', 0):>+10,.2f}"
        )
    if not rows:
        print("  (no open positions)")


if __name__ == "__main__":
    main()
