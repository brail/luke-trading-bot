"""Phase 0a — Strategy B (LLM event-driven) backtest.

No param sweep: strategy params are fixed. Runs directly on OOS test set.
Requires ANTHROPIC_API_KEY in .env.

Usage:
    uv run python backtest/run_phase0a_b.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bot.data.historical import load_candles
from bot.strategies.llm_eventdriven import LLMEventDriven
from backtest.harness import BacktestHarness
from backtest.metrics import compute_metrics, pass_fail, print_report

COINS = ["BTC", "ETH", "SOL"]
TEST_START = datetime(2026, 2, 17, tzinfo=timezone.utc)
TEST_END   = datetime(2026, 4, 17, tzinfo=timezone.utc)

INITIAL_EQUITY = 1_000.0
COST_BPS       = 10.0


def main() -> None:
    print("Loading daily data for test period ...")
    test_data = {coin: load_candles(coin, "1d", TEST_START, TEST_END) for coin in COINS}

    for coin, df in test_data.items():
        print(f"  {coin}: {len(df)} daily bars ({TEST_START.date()} → {TEST_END.date()})")

    print(f"\nInitialising LLM strategy (model: claude-sonnet-4-6) ...")
    strategy = LLMEventDriven()

    # Count expected events before running (no cost here — purely from precomputed data)
    strategy.setup(test_data)
    total_events = sum(len(v) for v in strategy._events.values())
    print(f"Events detected on test set: {total_events} coin-days across {COINS}")
    for coin in COINS:
        n = len(strategy._events.get(coin, set()))
        print(f"  {coin}: {n} event days")

    print(f"\nRunning backtest (LLM calls will start now, hard cap ${strategy.__class__.__module__}.LLM_COST_CAP_USD) ...")

    result = BacktestHarness(test_data, strategy, INITIAL_EQUITY, COST_BPS).run()
    m  = compute_metrics(result)
    pf = pass_fail(m, llm_cost_usd=strategy.total_cost_usd)

    print_report("Strategy B — LLM event-driven (Sonnet 4.6)", m, pf)
    print(f"  LLM calls      : {strategy.llm_call_count}")
    print(f"  LLM total cost : ${strategy.total_cost_usd:.4f}")

    runs_dir = Path("runs")
    runs_dir.mkdir(exist_ok=True)
    report_path = runs_dir / "phase0a_B.md"
    with open(report_path, "w") as f:
        f.write("# Phase 0a — Strategy B results\n\n")
        f.write(f"- Date: {datetime.now(timezone.utc).date()}\n")
        f.write(f"- Model: claude-sonnet-4-6\n")
        f.write(f"- LLM calls: {strategy.llm_call_count}\n")
        f.write(f"- LLM cost: ${strategy.total_cost_usd:.4f}\n\n")
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
