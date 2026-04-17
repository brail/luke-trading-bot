from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import httpx
import pandas as pd

_INFO_URL = "https://api.hyperliquid.xyz/info"
_CHUNK = 5000  # max candles per Hyperliquid request
_DEFAULT_CACHE = Path(__file__).parent.parent.parent / "data" / "cache"


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _parse(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles).rename(
        columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "n": "n_trades"}
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["n_trades"] = df["n_trades"].astype(int)
    return df[["open", "high", "low", "close", "volume", "n_trades"]]


def load_candles(
    coin: str,
    interval: str,
    start: datetime,
    end: datetime,
    cache_dir: Path | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return OHLCV candles for *coin* between *start* and *end*, with Parquet cache.

    Paginates automatically for ranges that exceed 5000 candles.
    Results are cached per (coin, interval, start-date, end-date) to avoid re-fetching.
    """
    cache_dir = cache_dir or _DEFAULT_CACHE
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{coin}_{interval}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.parquet"

    if cache_path.exists() and not force_refresh:
        return pd.read_parquet(cache_path)

    start_ms, end_ms = _ms(start), _ms(end)
    all_candles: list[dict] = []

    with httpx.Client(timeout=30.0) as client:
        cursor = start_ms
        while cursor < end_ms:
            r = client.post(
                _INFO_URL,
                json={"type": "candleSnapshot", "req": {"coin": coin, "interval": interval, "startTime": cursor, "endTime": end_ms}},
            )
            r.raise_for_status()
            chunk: list[dict] = r.json()
            if not chunk:
                break
            all_candles.extend(chunk)
            if len(chunk) < _CHUNK:
                break
            cursor = chunk[-1]["t"] + 1  # next page starts after last candle open-time
            time.sleep(0.1)

    df = _parse(all_candles)
    df.to_parquet(cache_path)
    return df
