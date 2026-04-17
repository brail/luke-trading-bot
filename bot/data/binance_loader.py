"""Binance historical OHLCV loader via CCXT with Parquet cache.

Fetches public market data — no API credentials needed.
Cache path: data/cache/binance_{coin}_{interval}_{start_date}_{end_date}.parquet
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

CACHE_DIR = Path("data/cache")
FETCH_LIMIT = 1000  # Binance max bars per request


def load_binance_candles(
    coin: str,
    interval: str,
    start: datetime,
    end: datetime,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch OHLCV bars for *coin*/USDT from Binance spot market.

    Returns DataFrame with UTC DatetimeIndex and columns: open, high, low, close, volume.
    Data is cached as Parquet to avoid repeated API calls.
    """
    import ccxt  # lazy import so the module loads without ccxt installed in tests

    cache_dir = cache_dir or CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_path = cache_dir / f"binance_{coin}_{interval}_{start.date()}_{end.date()}.parquet"

    if cache_path.exists() and not force_refresh:
        return pd.read_parquet(cache_path)

    symbol = f"{coin}/USDT"
    exchange = ccxt.binance({"enableRateLimit": True})

    since_ms = int(start.timestamp() * 1000)
    until_ms = int(end.timestamp() * 1000)

    all_bars: list[list] = []
    while since_ms < until_ms:
        bars = exchange.fetch_ohlcv(symbol, interval, since=since_ms, limit=FETCH_LIMIT)
        if not bars:
            break
        # Filter out bars beyond end
        bars = [b for b in bars if b[0] < until_ms]
        all_bars.extend(bars)
        if len(bars) < FETCH_LIMIT:
            break
        since_ms = all_bars[-1][0] + 1

    if not all_bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="first")]

    df.to_parquet(cache_path)
    return df
