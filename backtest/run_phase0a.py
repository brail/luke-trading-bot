"""Phase 0a — Strategy A (Donchian ATR) backtest.

Param sweep on TRAIN set, then locked evaluation on OOS TEST set.
Pass/fail criteria: docs/phase-0a-plan.md.

Usage:
    uv run python backtest/run_phase0a.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bot.data.historical import load_candles
from bot.strategies.donchian_atr import DonchianATR
from backtest.harness import BacktestHarness
from backtest.metrics import compute_metrics, pass_fail, print_report

COINS = ["BTC", "ETH", "SOL"]
TRAIN_START = datetime(2025, 10, 17, tzinfo=timezone.utc)
TRAIN_END   = datetime(2026,  2, 17, tzinfo=timezone.utc)
TEST_START  = TRAIN_END
TEST_END    = datetime(2026,  4, 17, tzinfo=timezone.utc)

INITIAL_EQUITY = 1_000.0
COST_BPS       = 10.0

ENTRY_WINDOWS     = [10, 20, 40]
CHANDELIER_MULTS  = [2.0, 3.0, 4.0]


def load_data(start: datetime, end: datetime) -> dict:
    return {coin: load_candles(coin, "1d", start, end) for coin in COINS}


def sweep_train(train_data: dict) -> tuple[int, float, float]:
    """Return (best entry_window, best chandelier_mult, best_sharpe) from train set."""
    best = (-999.0, 10, 3.0)
    print("Param sweep on TRAIN set:")
    for ew in ENTRY_WINDOWS:
        for cm in CHANDELIER_MULTS:
            strategy = DonchianATR(entry_window=ew, chandelier_mult=cm)
            result = BacktestHarness(train_data, strategy, INITIAL_EQUITY, COST_BPS).run()
            m = compute_metrics(result)
            sharpe = m["sharpe"]
            print(f"  entry_window={ew:2d}  chandelier_mult={cm:.1f}  "
                  f"Sharpe={sharpe:6.3f}  MaxDD={m['max_dd_pct']:6.2f}%  trades={m['n_trades']}")
            if sharpe > best[0]:
                best = (sharpe, ew, cm)
    return best[1], best[2], best[0]


def main() -> None:
    print("Loading data ...")
    train_data = load_data(TRAIN_START, TRAIN_END)
    test_data  = load_data(TEST_START,  TEST_END)

    print(f"\nTrain period : {TRAIN_START.date()} → {TRAIN_END.date()}")
    print(f"Test  period : {TEST_START.date()} → {TEST_END.date()}")
    for coin, df in train_data.items():
        print(f"  {coin}: {len(df)} daily bars (train) / {len(test_data[coin])} bars (test)")

    print()
    best_ew, best_cm, best_train_sharpe = sweep_train(train_data)
    print(f"\nBest train params: entry_window={best_ew}  chandelier_mult={best_cm}  Sharpe={best_train_sharpe:.3f}")
    print("Params locked. Running OOS test set ...")

    strategy = DonchianATR(entry_window=best_ew, chandelier_mult=best_cm)
    result   = BacktestHarness(test_data, strategy, INITIAL_EQUITY, COST_BPS).run()
    m        = compute_metrics(result)
    pf       = pass_fail(m)

    print_report(f"Strategy A — Donchian ATR  (entry={best_ew}, mult={best_cm})", m, pf)

    # Save result
    runs_dir = Path("runs")
    runs_dir.mkdir(exist_ok=True)
    report_path = runs_dir / "phase0a_A.md"
    with open(report_path, "w") as f:
        f.write(f"# Phase 0a — Strategy A results\n\n")
        f.write(f"- Date: {datetime.now(timezone.utc).date()}\n")
        f.write(f"- Best train params: entry_window={best_ew}, chandelier_mult={best_cm}\n")
        f.write(f"- Train Sharpe: {best_train_sharpe:.3f}\n\n")
        f.write(f"## OOS test metrics\n\n")
        f.write(f"| Metric | Value |\n|---|---|\n")
        for k, v in m.items():
            f.write(f"| {k} | {v} |\n")
        f.write(f"\n## Pass/fail\n\n")
        f.write(f"**Overall: {'PASS' if pf['pass'] else 'FAIL'}**\n\n")
        for k, v in pf["checks"].items():
            f.write(f"- {'✓' if v else '✗'} {k}\n")
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
