"""Print top-N Hyperliquid perpetuals by 24h notional volume."""

from __future__ import annotations

from bot.data.hyperliquid_client import HyperliquidClient

TOP_N = 10


def main() -> None:
    with HyperliquidClient() as client:
        universe, ctxs = client.meta_and_asset_ctxs()

    rows = []
    for u, c in zip(universe, ctxs, strict=True):
        vol_usd = float(c.get("dayNtlVlm", 0))
        oi_coins = float(c.get("openInterest", 0))
        mark = float(c.get("markPx", 0))
        funding_hourly = float(c.get("funding", 0))
        rows.append((u["name"], vol_usd, oi_coins * mark, funding_hourly, mark))

    rows.sort(key=lambda r: r[1], reverse=True)

    header = f"{'Coin':<10} {'Vol 24h USD':>18} {'OI USD':>18} {'Funding 1h':>12} {'Mark':>12}"
    print(header)
    print("-" * len(header))
    for name, vol, oi, funding, mark in rows[:TOP_N]:
        print(f"{name:<10} {vol:>18,.0f} {oi:>18,.0f} {funding:>12.6f} {mark:>12,.4f}")


if __name__ == "__main__":
    main()
