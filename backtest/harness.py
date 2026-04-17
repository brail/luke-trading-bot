from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from bot.risk.manager import circuit_breaker_hit


class Strategy(Protocol):
    def setup(self, data: dict[str, pd.DataFrame]) -> None: ...
    def signal(self, coin: str, t: pd.Timestamp) -> "Signal": ...


@dataclass
class Signal:
    action: str  # "open_long" | "close" | "hold"
    stop_price: float = 0.0
    size_usd: float = 0.0  # required for open_long


@dataclass
class Position:
    coin: str
    entry_price: float
    entry_time: pd.Timestamp
    size_usd: float
    stop_price: float


@dataclass
class Trade:
    coin: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    size_usd: float
    pnl_usd: float  # net of round-trip transaction costs
    exit_reason: str  # "stop" | "signal" | "circuit_breaker" | "end_of_backtest"


@dataclass
class BacktestResult:
    equity_curve: pd.Series  # total equity (cash + mark-to-market) indexed by timestamp
    trades: list[Trade]
    initial_equity: float


class BacktestHarness:
    """Event-driven backtest engine.

    Iterates chronologically over *data*, calling *strategy*.signal() each bar.
    Signals generated at bar T execute at bar T+1 open (avoids lookahead).
    Intraday stops are checked against each bar's low.
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
                lo = float(bar["low"])
                cl = float(bar["close"])

                # 1. Execute pending signal from previous bar (at today's open)
                if coin in pending:
                    sig = pending.pop(coin)
                    if sig.action == "open_long" and coin not in positions and not cb:
                        cash -= sig.size_usd * (1 + self.cost)
                        positions[coin] = Position(coin, op, t, sig.size_usd, sig.stop_price)
                    elif sig.action == "close" and coin in positions:
                        cash += self._close(coin, op, t, "signal", positions, trades)

                # 2. Check stop hit: low crossed below trailing stop
                if coin in positions and lo <= positions[coin].stop_price:
                    cash += self._close(coin, positions[coin].stop_price, t, "stop", positions, trades)

                # 3. Circuit breaker: close position and halt new signals
                if cb and coin in positions:
                    cash += self._close(coin, cl, t, "circuit_breaker", positions, trades)
                    pending.pop(coin, None)
                    continue

                # 4. Generate signal for next bar; ratchet trailing stop upward
                sig = self.strategy.signal(coin, t)
                if coin in positions and sig.stop_price > positions[coin].stop_price:
                    positions[coin].stop_price = sig.stop_price
                if sig.action in ("open_long", "close"):
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

    def _mark_equity(self, cash: float, positions: dict[str, Position], t: pd.Timestamp) -> float:
        mark = sum(
            pos.size_usd * float(self.data[c].loc[t, "close"]) / pos.entry_price
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
        proceeds = pos.size_usd * (price / pos.entry_price) * (1 - self.cost)
        pnl = proceeds - pos.size_usd * (1 + self.cost)
        trades.append(Trade(coin, pos.entry_time, t, pos.entry_price, price, pos.size_usd, pnl, reason))
        return proceeds
