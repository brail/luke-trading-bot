"""LLM-in-the-loop event-driven strategy using Claude Sonnet 4.6.

The LLM is called only when a significant market event is detected on 1h data:
  1. New 20-day high or low
  2. Hourly return > 2σ of rolling 20-day volatility
  3. Hourly volume > 3× rolling 20-day average

The LLM decides action and conviction. Stop placement and position sizing
are handled deterministically by bot.risk.manager — the LLM cannot bypass limits.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pandas as pd
from dotenv import load_dotenv

from backtest.harness import Signal
from bot.data.historical import load_candles
from bot.risk.manager import atr, chandelier_stop, position_size_usd

LLM_COST_CAP_USD = 50.0
MODEL = "claude-sonnet-4-6"
EVENT_WINDOW_H = 480  # 20 days of 1h bars

SYSTEM_PROMPT = """You are an algorithmic trading assistant for a long-only crypto bot.

Assets: BTC, ETH, SOL perpetuals (long-only, no shorting).
You are called only when a significant market event fires.
Position sizing, trailing stops, and all risk limits are managed externally.

Your job: decide whether to open a long, close an existing long, or hold.
Use the trading_decision tool. Set conviction 0.0–1.0 (fraction of max position size).
Be concise in reasoning (one sentence max)."""

TOOL = {
    "name": "trading_decision",
    "description": "Submit a trading decision for the triggered event.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["open_long", "close", "hold"]},
            "conviction": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "reasoning": {"type": "string"},
        },
        "required": ["action", "conviction", "reasoning"],
    },
}


class LLMEventDriven:
    def __init__(self, model: str = MODEL, event_window_h: int = EVENT_WINDOW_H) -> None:
        self.model = model
        self.event_window_h = event_window_h
        self.total_cost_usd = 0.0
        self.llm_call_count = 0

        self._daily: dict[str, pd.DataFrame] = {}
        self._atr_s: dict[str, pd.Series] = {}
        self._stop_s: dict[str, pd.Series] = {}
        self._events: dict[str, set] = {}         # coin → set of dates with events
        self._event_desc: dict[str, dict] = {}    # coin → {date: [event_str, ...]}
        self._has_pos: dict[str, bool] = {}
        self._client = None

    # ------------------------------------------------------------------
    # Strategy Protocol
    # ------------------------------------------------------------------

    def setup(self, data: dict[str, pd.DataFrame]) -> None:
        load_dotenv(override=True)  # override=True needed: shell may export ANTHROPIC_API_KEY="" (empty)
        from anthropic import Anthropic
        self._client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        self._daily = data
        for coin, df in data.items():
            atr_s = atr(df["high"], df["low"], df["close"], 22)
            self._atr_s[coin] = atr_s
            self._stop_s[coin] = chandelier_stop(df["high"], atr_s, 22, 3.0)
            self._has_pos[coin] = False
            self._compute_events(coin, df)

    def signal(self, coin: str, t: pd.Timestamp, equity: float) -> Signal:
        if coin not in self._daily or t not in self._daily[coin].index:
            return Signal("hold")

        stop = float(self._stop_s[coin].get(t, float("nan")))
        atr_val = float(self._atr_s[coin].get(t, float("nan")))
        if pd.isna(stop) or pd.isna(atr_val):
            return Signal("hold")

        close = float(self._daily[coin].loc[t, "close"])
        event_today = t.date() in self._events.get(coin, set())

        if not event_today:
            return Signal("hold", stop_price=stop)

        # Event detected — call LLM
        decision = self._call_llm(coin, t)
        action = decision.get("action", "hold")
        conviction = float(decision.get("conviction", 0.0))

        if action == "open_long" and not self._has_pos[coin]:
            size = position_size_usd(atr_val, close, equity) * max(0.0, min(1.0, conviction))
            self._has_pos[coin] = True
            return Signal("open_long", stop_price=stop, size_usd=size)

        if action == "close" and self._has_pos[coin]:
            self._has_pos[coin] = False
            return Signal("close", stop_price=stop)

        return Signal("hold", stop_price=stop)

    # ------------------------------------------------------------------
    # Event detection
    # ------------------------------------------------------------------

    def _compute_events(self, coin: str, df: pd.DataFrame) -> None:
        """Detect events on daily data (use daily bars since 1h already cached; saves time)."""
        w = self.event_window_h // 24  # convert to daily periods (~20 days)

        hh = df["high"].rolling(w, min_periods=w).max().shift(1)
        ll = df["low"].rolling(w, min_periods=w).min().shift(1)
        new_high = df["close"] > hh
        new_low = df["close"] < ll

        ret = df["close"].pct_change()
        vol_20d = ret.rolling(w, min_periods=w).std()
        big_move = ret.abs() > 2 * vol_20d

        vol_avg = df["volume"].rolling(w, min_periods=w).mean()
        vol_spike = df["volume"] > 3 * vol_avg

        dates: set = set()
        desc: dict = {}
        for t, row in df.iterrows():
            d = t.date()
            fired = []
            if new_high.get(t, False):
                fired.append("20D_HIGH")
            if new_low.get(t, False):
                fired.append("20D_LOW")
            if big_move.get(t, False):
                fired.append("BIG_MOVE")
            if vol_spike.get(t, False):
                fired.append("VOL_SPIKE")
            if fired:
                dates.add(d)
                desc[d] = fired

        self._events[coin] = dates
        self._event_desc[coin] = desc

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    def _call_llm(self, coin: str, t: pd.Timestamp) -> dict:
        if self.total_cost_usd >= LLM_COST_CAP_USD:
            return {"action": "hold", "conviction": 0.0, "reasoning": "cost cap reached"}

        try:
            context = self._format_context(coin, t)
            response = self._client.messages.create(
                model=self.model,
                max_tokens=300,
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": context}],
                tools=[TOOL],
                tool_choice={"type": "tool", "name": "trading_decision"},
            )
            self._track_cost(response.usage)
            self.llm_call_count += 1
            tool_block = next(b for b in response.content if b.type == "tool_use")
            return tool_block.input
        except Exception as exc:
            print(f"  [LLM] call failed for {coin}@{t.date()}: {exc}")
            return {"action": "hold", "conviction": 0.0, "reasoning": f"error: {exc}"}

    def _format_context(self, coin: str, t: pd.Timestamp) -> str:
        df = self._daily[coin]
        loc = df.index.searchsorted(t)
        window = df.iloc[max(0, loc - 59) : loc + 1]

        rows = "\n".join(
            f"{ts.date()}|{r['open']:.2f}|{r['high']:.2f}|{r['low']:.2f}|{r['close']:.2f}|{r['volume']:.0f}"
            for ts, r in window.iterrows()
        )
        events_str = ", ".join(self._event_desc.get(coin, {}).get(t.date(), ["UNKNOWN"]))
        position_str = "LONG (open)" if self._has_pos.get(coin) else "NONE"

        return (
            f"Coin: {coin}\n"
            f"Date: {t.date()}\n"
            f"Current position: {position_str}\n"
            f"Triggering events: {events_str}\n\n"
            f"Daily OHLCV (oldest first) — Date|Open|High|Low|Close|Volume:\n{rows}"
        )

    def _track_cost(self, usage) -> None:
        inp = getattr(usage, "input_tokens", 0)
        out = getattr(usage, "output_tokens", 0)
        cache_write = getattr(usage, "cache_creation_input_tokens", 0)
        cache_read = getattr(usage, "cache_read_input_tokens", 0)
        non_cached = inp - cache_write - cache_read
        cost = (
            non_cached * 3e-6
            + cache_write * 3.75e-6
            + cache_read * 0.3e-6
            + out * 15e-6
        )
        self.total_cost_usd += cost
