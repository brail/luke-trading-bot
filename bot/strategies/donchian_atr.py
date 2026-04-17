from __future__ import annotations

import pandas as pd

from backtest.harness import Signal
from bot.risk.manager import atr, chandelier_stop, position_size_usd


class DonchianATR:
    """Donchian channel breakout with ATR-based position sizing and Chandelier trailing stop.

    Entry:  close breaks above the prior *entry_window* bars' highest high.
    Exit:   trailing Chandelier stop (highest-high[chandelier_periods] - mult * ATR).
    Sizing: vol-targeting (15% ann. vol) capped by 1% max risk at stop distance.
    """

    def __init__(
        self,
        entry_window: int = 20,
        chandelier_periods: int = 22,
        chandelier_mult: float = 3.0,
    ) -> None:
        self.entry_window = entry_window
        self.chandelier_periods = chandelier_periods
        self.chandelier_mult = chandelier_mult

        self._atr: dict[str, pd.Series] = {}
        self._stop: dict[str, pd.Series] = {}
        self._entry: dict[str, pd.Series] = {}
        self._data: dict[str, pd.DataFrame] = {}

    def setup(self, data: dict[str, pd.DataFrame]) -> None:
        self._data = data
        for coin, df in data.items():
            atr_s = atr(df["high"], df["low"], df["close"], self.chandelier_periods)
            self._atr[coin] = atr_s
            self._stop[coin] = chandelier_stop(df["high"], atr_s, self.chandelier_periods, self.chandelier_mult)
            # Entry when today's close exceeds yesterday's Donchian high (shift(1) → no lookahead)
            donchian_high = df["high"].rolling(self.entry_window, min_periods=self.entry_window).max().shift(1)
            self._entry[coin] = df["close"] > donchian_high

    def signal(self, coin: str, t: pd.Timestamp, equity: float) -> Signal:
        if coin not in self._data or t not in self._data[coin].index:
            return Signal("hold")

        stop = float(self._stop[coin].get(t, float("nan")))
        atr_val = float(self._atr[coin].get(t, float("nan")))
        entry_triggered = bool(self._entry[coin].get(t, False))
        close = float(self._data[coin].loc[t, "close"])

        if pd.isna(stop) or pd.isna(atr_val):
            return Signal("hold")

        if entry_triggered:
            size = position_size_usd(atr_val, close, equity,
                                     stop_mult=self.chandelier_mult)
            return Signal("open_long", stop_price=stop, size_usd=size)

        return Signal("hold", stop_price=stop)
