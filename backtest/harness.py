from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from bot.risk.manager import circuit_breaker_hit


class Strategy(Protocol):
    def setup(self, data: dict[str, pd.DataFrame]) -> None: ...
    def signal(self, coin: str, t: pd.Timestamp, equity: float) -> "Signal": ...


@dataclass
class Signal:
    action: str  # "open_long" | "open_short" | "close" | "hold"
    stop_price: float = 0.0
    size_usd: float = 0.0  # required for open_long / open_short


@dataclass
class Position:
    coin: str
    entry_price: float
    entry_time: pd.Timestamp
    size_usd: float
    stop_price: float
    side: str = "long"  # "long" | "short"


@dataclass
class Trade:
    coin: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    size_usd: float
    pnl_usd: float  # net of round-trip transaction costs
    exit_reason: str  # "stop" | "flip" | "signal" | "circuit_breaker" | "end_of_backtest"
    side: str = "long"  # "long" | "short"


@dataclass
class BacktestResult:
    equity_curve: pd.Series  # total equity indexed by timestamp
    trades: list[Trade]
    initial_equity: float


class BacktestHarness:
    """Event-driven backtest engine supporting long and short positions.

    Signals generated at bar T execute at bar T+1 open (avoids lookahead).
    Long stops are checked against the bar's low; short stops against the bar's high.
    Flipping (long → short or short → long) closes the existing position at the
    same bar's open before entering the new one.
    """

    def __init__(
        self,
        data: dict[str, pd.DataFrame],
        strategy: Strategy,
        initial_equity: float = 1_000.0,
        cost_bps: float = 10.0,
        daily_dd_limit: float = 0.03,
        weekly_dd_limit: float = 0.06,
        monthly_dd_limit: float = 0.12,
    ) -> None:
        self.data = data
        self.strategy = strategy
        self.initial_equity = initial_equity
        self.cost = cost_bps / 10_000
        self.dd = dict(daily=daily_dd_limit, weekly=weekly_dd_limit, monthly=monthly_dd_limit)

    def run(self) -> BacktestResult:
        self.strategy.setup(self.data)

        index: list[pd.Timestamp] = sorted(set().union(*[set(df.index) for df in self.data.values()]))
        coins = list(self.data.keys())

        cash = self.initial_equity
        positions: dict[str, Position] = {}
        pending: dict[str, Signal] = {}  # signals queued for next bar
        trades: list[Trade] = []
        equity_curve: dict[pd.Timestamp, float] = {}

        day_start_eq = week_start_eq = month_start_eq = self.initial_equity
        prev_day = prev_week = prev_month = None

        for t in index:
            eq = self._mark_equity(cash, positions, t)

            day = t.date()
            week = t.isocalendar()[:2]
            month = (t.year, t.month)

            if prev_day is None:
                prev_day, prev_week, prev_month = day, week, month
            if day != prev_day:
                day_start_eq = eq
                prev_day = day
            if week != prev_week:
                week_start_eq = eq
                prev_week = week
            if month != prev_month:
                month_start_eq = eq
                prev_month = month

            cb = circuit_breaker_hit(
                eq, day_start_eq, week_start_eq, month_start_eq,
                self.dd["daily"], self.dd["weekly"], self.dd["monthly"],
            )

            for coin in coins:
                df = self.data[coin]
                if t not in df.index:
                    continue
                bar = df.loc[t]
                op = float(bar["open"])
                hi = float(bar["high"])
                lo = float(bar["low"])
                cl = float(bar["close"])

                # 1. Execute pending signal from previous bar (at today's open)
                if coin in pending:
                    sig = pending.pop(coin)
                    if sig.action in ("open_long", "open_short") and not cb:
                        new_side = "long" if sig.action == "open_long" else "short"
                        # Flip: close opposite position first
                        if coin in positions and positions[coin].side != new_side:
                            cash += self._close(coin, op, t, "flip", positions, trades)
                        # Open if not already in this direction
                        if coin not in positions:
                            cash -= sig.size_usd * (1 + self.cost)
                            positions[coin] = Position(coin, op, t, sig.size_usd, sig.stop_price, new_side)
                    elif sig.action == "close" and coin in positions:
                        cash += self._close(coin, op, t, "signal", positions, trades)

                # 2. Check stop hit: long → low crosses below stop; short → high crosses above stop
                if coin in positions:
                    pos = positions[coin]
                    stop_hit = (
                        (pos.side == "long" and lo <= pos.stop_price) or
                        (pos.side == "short" and hi >= pos.stop_price)
                    )
                    if stop_hit:
                        cash += self._close(coin, pos.stop_price, t, "stop", positions, trades)

                # 3. Circuit breaker: close position and halt new signals
                if cb and coin in positions:
                    cash += self._close(coin, cl, t, "circuit_breaker", positions, trades)
                    pending.pop(coin, None)
                    continue

                # 4. Generate signal for next bar; ratchet trailing stop in profitable direction
                sig = self.strategy.signal(coin, t, eq)
                if coin in positions:
                    pos = positions[coin]
                    if sig.stop_price > 0:
                        if pos.side == "long" and sig.stop_price > pos.stop_price:
                            pos.stop_price = sig.stop_price
                        elif pos.side == "short" and sig.stop_price < pos.stop_price:
                            pos.stop_price = sig.stop_price
                if sig.action in ("open_long", "open_short", "close"):
                    pending[coin] = sig

            equity_curve[t] = self._mark_equity(cash, positions, t)

        # Close remaining positions at backtest end
        last_t = index[-1]
        for coin in list(positions):
            exit_px = (
                float(self.data[coin].loc[last_t, "close"])
                if last_t in self.data[coin].index
                else positions[coin].entry_price
            )
            cash += self._close(coin, exit_px, last_t, "end_of_backtest", positions, trades)

        return BacktestResult(pd.Series(equity_curve), trades, self.initial_equity)

    def _return_mult(self, pos: Position, price: float) -> float:
        """Position value relative to size_usd. Long: grows with price; short: grows as price falls."""
        r = price / pos.entry_price
        return r if pos.side == "long" else 2.0 - r

    def _mark_equity(self, cash: float, positions: dict[str, Position], t: pd.Timestamp) -> float:
        mark = sum(
            pos.size_usd * self._return_mult(pos, float(self.data[c].loc[t, "close"]))
            for c, pos in positions.items()
            if t in self.data[c].index
        )
        return cash + mark

    def _close(
        self,
        coin: str,
        price: float,
        t: pd.Timestamp,
        reason: str,
        positions: dict[str, Position],
        trades: list[Trade],
    ) -> float:
        """Close position, record trade. Returns cash proceeds net of exit cost."""
        pos = positions.pop(coin)
        mult = self._return_mult(pos, price)
        proceeds = pos.size_usd * mult * (1 - self.cost)
        pnl = proceeds - pos.size_usd * (1 + self.cost)
        trades.append(Trade(
            coin, pos.entry_time, t, pos.entry_price, price,
            pos.size_usd, pnl, reason, pos.side,
        ))
        return proceeds
