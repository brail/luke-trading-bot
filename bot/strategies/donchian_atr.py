from __future__ import annotations

import math

import pandas as pd

from backtest.harness import Signal
from bot.risk.manager import atr, chandelier_stop, chandelier_stop_short, position_size_usd

_NAN = float("nan")


class DonchianATR:
    """Bidirectional Donchian channel breakout with ATR-based sizing and Chandelier stops.

    Long entry:  close breaks above the prior *entry_window* bars' highest high.
    Short entry: close breaks below the prior *entry_window* bars' lowest low.
    Long exit:   Chandelier long stop  = HH(chandelier_periods) − mult × ATR.
    Short exit:  Chandelier short stop = LL(chandelier_periods) + mult × ATR.
    Sizing:      vol-targeting (15% ann. vol) capped by 1% max risk at stop distance.
    """

    def __init__(
        self,
        entry_window: int = 45,
        chandelier_periods: int = 22,
        chandelier_mult: float = 3.0,
    ) -> None:
        self.entry_window = entry_window
        self.chandelier_periods = chandelier_periods
        self.chandelier_mult = chandelier_mult

        self._atr: dict[str, pd.Series] = {}
        self._long_stop: dict[str, pd.Series] = {}
        self._short_stop: dict[str, pd.Series] = {}
        self._long_entry: dict[str, pd.Series] = {}
        self._short_entry: dict[str, pd.Series] = {}
        self._data: dict[str, pd.DataFrame] = {}
        self._side: dict[str, str | None] = {}  # last signalled direction per coin

    def setup(self, data: dict[str, pd.DataFrame]) -> None:
        self._data = data
        for coin, df in data.items():
            atr_s = atr(df["high"], df["low"], df["close"], self.chandelier_periods)
            self._atr[coin] = atr_s
            self._long_stop[coin] = chandelier_stop(
                df["high"], atr_s, self.chandelier_periods, self.chandelier_mult
            )
            self._short_stop[coin] = chandelier_stop_short(
                df["low"], atr_s, self.chandelier_periods, self.chandelier_mult
            )
            # shift(1): entry triggered by yesterday's breakout → executed at today's open
            donchian_high = df["high"].rolling(self.entry_window, min_periods=self.entry_window).max().shift(1)
            donchian_low = df["low"].rolling(self.entry_window, min_periods=self.entry_window).min().shift(1)
            self._long_entry[coin] = df["close"] > donchian_high
            self._short_entry[coin] = df["close"] < donchian_low
            self._side[coin] = None

    def signal(self, coin: str, t: pd.Timestamp, equity: float) -> Signal:
        if coin not in self._data or t not in self._data[coin].index:
            return Signal("hold")

        atr_val = float(self._atr[coin].get(t, _NAN))
        if math.isnan(atr_val):
            return Signal("hold")

        close = float(self._data[coin].loc[t, "close"])
        long_entry = bool(self._long_entry[coin].get(t, False))
        short_entry = bool(self._short_entry[coin].get(t, False))
        long_stop = float(self._long_stop[coin].get(t, _NAN))
        short_stop = float(self._short_stop[coin].get(t, _NAN))

        if long_entry and not math.isnan(long_stop):
            self._side[coin] = "long"
            size = position_size_usd(atr_val, close, equity, stop_mult=self.chandelier_mult)
            return Signal("open_long", stop_price=long_stop, size_usd=size)

        if short_entry and not math.isnan(short_stop):
            self._side[coin] = "short"
            size = position_size_usd(atr_val, close, equity, stop_mult=self.chandelier_mult)
            return Signal("open_short", stop_price=short_stop, size_usd=size)

        # Hold: ratchet the stop for whichever side we're currently on
        side = self._side[coin]
        if side == "long" and not math.isnan(long_stop):
            return Signal("hold", stop_price=long_stop)
        if side == "short" and not math.isnan(short_stop):
            return Signal("hold", stop_price=short_stop)
        return Signal("hold")
