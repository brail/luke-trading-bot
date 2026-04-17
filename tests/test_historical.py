from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import pytest

from bot.data.historical import load_candles

EXPECTED_COLS = ["open", "high", "low", "close", "volume", "n_trades"]


def test_fetch_btc_1h(tmp_path: Path) -> None:
    """Fetch 24h of BTC 1h candles from live Hyperliquid API."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=1)
    df = load_candles("BTC", "1h", start, end, cache_dir=tmp_path)

    assert list(df.columns) == EXPECTED_COLS
    assert len(df) >= 20
    assert df.index.tz is not None
    assert (df["high"] >= df["low"]).all()
    assert (df["close"] > 0).all()


def test_cache_hit(tmp_path: Path) -> None:
    """Second call returns data from disk without re-fetching."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=6)

    df1 = load_candles("ETH", "1h", start, end, cache_dir=tmp_path)
    parquet_files = list(tmp_path.glob("*.parquet"))
    assert len(parquet_files) == 1

    df2 = load_candles("ETH", "1h", start, end, cache_dir=tmp_path)
    pd.testing.assert_frame_equal(df1, df2)


def test_force_refresh_overwrites_cache(tmp_path: Path) -> None:
    """force_refresh=True re-fetches and overwrites existing Parquet file."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=3)

    load_candles("SOL", "1h", start, end, cache_dir=tmp_path)
    path = list(tmp_path.glob("*.parquet"))[0]
    mtime_before = path.stat().st_mtime

    load_candles("SOL", "1h", start, end, cache_dir=tmp_path, force_refresh=True)
    assert path.stat().st_mtime >= mtime_before
