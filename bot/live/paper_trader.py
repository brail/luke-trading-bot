"""Paper trading engine for Phase 1.

Runs every 4h. Fetches real-time 4h bars from Hyperliquid, applies the
DonchianATR strategy, and simulates fills — no real orders are placed.

State is persisted to a JSON file so each run picks up exactly where the
previous one left off (positions, pending signals, equity, trade log).

Execution model mirrors the backtest:
  signal at bar T close  →  fill at bar T+1 open
  stops checked against bar T+1 high/low

Usage (called by run_paper.py):
    trader = PaperTrader(state_path="state/paper_state.json")
    trader.run()
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from dotenv import load_dotenv

from bot.data.historical import load_candles
from bot.risk.manager import atr, chandelier_stop, chandelier_stop_short, position_size_usd
from bot.strategies.donchian_atr import DonchianATR
from bot.live.notifier import notify_trade_open, notify_trade_close, notify_summary

load_dotenv(override=True)

COINS = ["BTC", "ETH", "SOL"]
INTERVAL = "4h"
LOOKBACK_BARS = 200       # bars of history fetched each run (> entry_window + chandelier_periods)
COST_BPS = 10.0           # round-trip transaction cost per side
INITIAL_EQUITY = 1_000.0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {
        "equity": INITIAL_EQUITY,
        "positions": {},   # coin → {side, entry_price, stop_price, size_usd, entry_time}
        "pending": {},     # coin → {action, stop_price, size_usd}
        "trades": [],
        "last_bar_time": None,
    }


def _save_state(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str))


def _fetch_data(end: datetime) -> dict[str, pd.DataFrame]:
    start = end - timedelta(hours=LOOKBACK_BARS * 4)
    data = {}
    for coin in COINS:
        df = load_candles(coin, INTERVAL, start, end, force_refresh=True)
        if not df.empty:
            data[coin] = df
    return data


def _return_mult(side: str, entry_price: float, exit_price: float) -> float:
    r = exit_price / entry_price
    return r if side == "long" else 2.0 - r


def _close_position(
    state: dict,
    coin: str,
    exit_price: float,
    exit_time: str,
    reason: str,
) -> None:
    cost = COST_BPS / 10_000
    pos = state["positions"].pop(coin)
    mult = _return_mult(pos["side"], pos["entry_price"], exit_price)
    proceeds = pos["size_usd"] * mult * (1 - cost)
    pnl = proceeds - pos["size_usd"] * (1 + cost)
    state["equity"] += proceeds
    state["trades"].append({
        "coin": coin,
        "side": pos["side"],
        "entry_time": pos["entry_time"],
        "exit_time": exit_time,
        "entry_price": pos["entry_price"],
        "exit_price": exit_price,
        "size_usd": pos["size_usd"],
        "pnl_usd": round(pnl, 4),
        "exit_reason": reason,
    })
    print(f"  CLOSED {coin} {pos['side'].upper()} @ {exit_price:.2f}  pnl={pnl:+.2f}  reason={reason}")
    notify_trade_close(coin, pos["side"], pos["entry_price"], exit_price, pnl, reason)


def _open_position(
    state: dict,
    coin: str,
    side: str,
    open_price: float,
    stop_price: float,
    size_usd: float,
    entry_time: str,
) -> None:
    cost = COST_BPS / 10_000
    state["equity"] -= size_usd * (1 + cost)
    state["positions"][coin] = {
        "side": side,
        "entry_price": open_price,
        "stop_price": stop_price,
        "size_usd": size_usd,
        "entry_time": entry_time,
    }
    print(f"  OPEN  {coin} {side.upper()} @ {open_price:.2f}  stop={stop_price:.2f}  size=${size_usd:.2f}")
    notify_trade_open(coin, side, open_price, stop_price, size_usd)


class PaperTrader:
    def __init__(
        self,
        state_path: str | Path = "state/paper_state.json",
        entry_window: int = 60,
        chandelier_mult: float = 3.0,
    ) -> None:
        self.state_path = Path(state_path)
        self.strategy = DonchianATR(entry_window=entry_window, chandelier_mult=chandelier_mult)

    def run(self) -> None:
        now = _now_utc()
        print(f"\n{'='*60}")
        print(f"  Paper trader run — {now.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"{'='*60}")

        state = _load_state(self.state_path)
        data = _fetch_data(now)

        if not data:
            print("  ERROR: no market data fetched.")
            return

        self.strategy.setup(data)

        # Current bar = last CLOSED bar (bar opens at T, closes at T+4h)
        # Discard bars that haven't closed yet to avoid lookahead on incomplete data
        bar_duration = pd.Timedelta(hours=4)
        now_ts = pd.Timestamp(now)
        all_times = sorted(set().union(*[set(df.index) for df in data.values()]))
        closed_times = [t for t in all_times if t + bar_duration <= now_ts]
        if not closed_times:
            print("  No closed bars available yet.")
            return
        current_t = closed_times[-1]
        current_t_str = str(current_t)

        if state["last_bar_time"] == current_t_str:
            print(f"  Already processed bar {current_t.date()} {current_t.time()} — nothing to do.")
            return

        print(f"  Processing bar: {current_t}")

        # ----------------------------------------------------------------
        # 1. Execute signals pending from previous bar (at current bar open)
        # ----------------------------------------------------------------
        for coin, sig in list(state["pending"].items()):
            if coin not in data or current_t not in data[coin].index:
                continue
            bar = data[coin].loc[current_t]
            open_price = float(bar["open"])
            t_str = current_t_str
            new_side = "long" if sig["action"] == "open_long" else "short"

            if sig["action"] in ("open_long", "open_short"):
                # Flip if opposite side open
                if coin in state["positions"] and state["positions"][coin]["side"] != new_side:
                    _close_position(state, coin, open_price, t_str, "flip")
                if coin not in state["positions"]:
                    _open_position(state, coin, new_side, open_price,
                                   sig["stop_price"], sig["size_usd"], t_str)
            elif sig["action"] == "close" and coin in state["positions"]:
                _close_position(state, coin, open_price, t_str, "signal")

        state["pending"] = {}

        # ----------------------------------------------------------------
        # 2. Check stops against current bar's high/low
        # ----------------------------------------------------------------
        for coin in list(state["positions"]):
            if coin not in data or current_t not in data[coin].index:
                continue
            pos = state["positions"][coin]
            bar = data[coin].loc[current_t]
            hi = float(bar["high"])
            lo = float(bar["low"])
            stop_hit = (
                (pos["side"] == "long"  and lo <= pos["stop_price"]) or
                (pos["side"] == "short" and hi >= pos["stop_price"])
            )
            if stop_hit:
                _close_position(state, coin, pos["stop_price"], current_t_str, "stop")

        # ----------------------------------------------------------------
        # 3. Generate signals for next bar + ratchet stops
        # ----------------------------------------------------------------
        eq = state["equity"] + sum(
            pos["size_usd"] * _return_mult(
                pos["side"], pos["entry_price"],
                float(data[coin].loc[current_t, "close"]) if coin in data and current_t in data[coin].index
                else pos["entry_price"]
            )
            for coin, pos in state["positions"].items()
        )

        new_pending: dict = {}
        for coin in COINS:
            if coin not in data or current_t not in data[coin].index:
                continue
            sig = self.strategy.signal(coin, current_t, eq)

            # Ratchet stop
            if coin in state["positions"]:
                pos = state["positions"][coin]
                if sig.stop_price > 0:
                    if pos["side"] == "long"  and sig.stop_price > pos["stop_price"]:
                        pos["stop_price"] = sig.stop_price
                    elif pos["side"] == "short" and sig.stop_price < pos["stop_price"]:
                        pos["stop_price"] = sig.stop_price

            if sig.action in ("open_long", "open_short", "close"):
                new_pending[coin] = {
                    "action": sig.action,
                    "stop_price": sig.stop_price,
                    "size_usd": sig.size_usd,
                }
                print(f"  SIGNAL {coin}: {sig.action.upper()}  stop={sig.stop_price:.2f}  → executes next bar")

        state["pending"] = new_pending
        state["last_bar_time"] = current_t_str

        _save_state(state, self.state_path)
        self._print_summary(state, data, current_t)

    def _print_summary(self, state: dict, data: dict, t: pd.Timestamp) -> None:
        # Mark-to-market equity
        mtm = sum(
            pos["size_usd"] * _return_mult(
                pos["side"], pos["entry_price"],
                float(data[coin].loc[t, "close"]) if coin in data and t in data[coin].index
                else pos["entry_price"]
            )
            for coin, pos in state["positions"].items()
        )
        total_eq = state["equity"] + mtm

        pnl_total = sum(t["pnl_usd"] for t in state["trades"])
        n_trades  = len(state["trades"])
        wins      = sum(1 for t in state["trades"] if t["pnl_usd"] > 0)

        print(f"\n  Equity (MTM) : ${total_eq:.2f}  (cash ${state['equity']:.2f})")
        print(f"  P&L total    : ${pnl_total:+.2f}  ({n_trades} closed trades, {wins}/{n_trades} wins)")

        if state["positions"]:
            print("  Open positions:")
            for coin, pos in state["positions"].items():
                close = float(data[coin].loc[t, "close"]) if coin in data and t in data[coin].index else pos["entry_price"]
                unrealised = pos["size_usd"] * (_return_mult(pos["side"], pos["entry_price"], close) - 1)
                print(f"    {coin} {pos['side'].upper()} entry={pos['entry_price']:.2f} "
                      f"stop={pos['stop_price']:.2f}  unrealised={unrealised:+.2f}")
        else:
            print("  Open positions: none")

        if state["pending"]:
            print("  Pending (next bar):", {k: v["action"] for k, v in state["pending"].items()})

        notify_summary(total_eq, INITIAL_EQUITY, n_trades, state["positions"])
