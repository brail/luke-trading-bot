"""Phase 0b — bidirectional Donchian on Binance 4h data (2020-2026).

Param sweep on TRAIN set (2020-2023), locked evaluation on OOS TEST set (2023-2026).
No API credentials needed — Binance public OHLCV data.

Usage:
    uv run python backtest/run_phase0b.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bot.data.binance_loader import load_binance_candles
from bot.strategies.donchian_atr import DonchianATR
from backtest.harness import BacktestHarness
from backtest.metrics import compute_metrics, pass_fail, print_report

COINS = ["BTC", "ETH", "SOL"]
TRAIN_START = datetime(2020, 1, 1, tzinfo=timezone.utc)
TRAIN_END   = datetime(2023, 1, 1, tzinfo=timezone.utc)
TEST_START  = TRAIN_END
TEST_END    = datetime(2026, 1, 1, tzinfo=timezone.utc)

INTERVAL = "4h"
INITIAL_EQUITY = 1_000.0
COST_BPS       = 10.0

# Param grid (4h bars: 30 = ~5 days, 45 = ~7.5 days, 60 = ~10 days)
ENTRY_WINDOWS    = [30, 45, 60]
CHANDELIER_MULTS = [2.0, 3.0]


def load_data(start: datetime, end: datetime) -> dict:
    data = {}
    for coin in COINS:
        print(f"  Loading {coin}/USDT {INTERVAL} {start.date()} → {end.date()} ...")
        df = load_binance_candles(coin, INTERVAL, start, end)
        print(f"    {len(df)} bars")
        data[coin] = df
    return data


def sweep_train(train_data: dict) -> tuple[int, float, float]:
    best = (-999.0, 30, 3.0)
    print("\nParam sweep on TRAIN set:")
    for ew in ENTRY_WINDOWS:
        for cm in CHANDELIER_MULTS:
            strategy = DonchianATR(entry_window=ew, chandelier_mult=cm)
            result = BacktestHarness(train_data, strategy, INITIAL_EQUITY, COST_BPS).run()
            m = compute_metrics(result)
            print(
                f"  entry_window={ew:2d}  mult={cm:.1f}  "
                f"Sharpe={m['sharpe']:6.3f}  MaxDD={m['max_dd_pct']:6.2f}%  "
                f"trades={m['n_trades']:3d}  return={m['net_return_pct']:+.2f}%"
            )
            if m["sharpe"] > best[0]:
                best = (m["sharpe"], ew, cm)
    return best[1], best[2], best[0]


def main() -> None:
    print("Loading TRAIN data ...")
    train_data = load_data(TRAIN_START, TRAIN_END)

    print("\nLoading TEST data ...")
    test_data = load_data(TEST_START, TEST_END)

    print(f"\nTrain period : {TRAIN_START.date()} → {TRAIN_END.date()}")
    print(f"Test  period : {TEST_START.date()} → {TEST_END.date()}")

    best_ew, best_cm, best_train_sharpe = sweep_train(train_data)
    print(f"\nBest train params: entry_window={best_ew}  mult={best_cm}  Sharpe={best_train_sharpe:.3f}")
    print("Params locked. Running OOS test set ...")

    strategy = DonchianATR(entry_window=best_ew, chandelier_mult=best_cm)
    result   = BacktestHarness(test_data, strategy, INITIAL_EQUITY, COST_BPS).run()
    m        = compute_metrics(result)
    pf       = pass_fail(m)

    print_report(f"Phase 0b — Donchian ATR bidirectional  (entry={best_ew}, mult={best_cm})", m, pf)

    runs_dir = Path("runs")
    runs_dir.mkdir(exist_ok=True)
    report_path = runs_dir / "phase0b.md"
    with open(report_path, "w") as f:
        f.write("# Phase 0b — Bidirectional Donchian ATR results\n\n")
        f.write(f"- Date: {datetime.now(timezone.utc).date()}\n")
        f.write(f"- Data: Binance spot {INTERVAL}, {COINS}\n")
        f.write(f"- Train: {TRAIN_START.date()} → {TRAIN_END.date()}\n")
        f.write(f"- Test:  {TEST_START.date()} → {TEST_END.date()}\n")
        f.write(f"- Best train params: entry_window={best_ew}, mult={best_cm}\n")
        f.write(f"- Train Sharpe: {best_train_sharpe:.3f}\n\n")
        f.write("## OOS test metrics\n\n| Metric | Value |\n|---|---|\n")
        for k, v in m.items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Pass/fail\n\n")
        f.write(f"**Overall: {'PASS' if pf['pass'] else 'FAIL'}**\n\n")
        for k, v in pf["checks"].items():
            f.write(f"- {'✓' if v else '✗'} {k}\n")
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
