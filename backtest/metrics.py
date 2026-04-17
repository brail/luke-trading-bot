from __future__ import annotations

import math

import pandas as pd

from backtest.harness import BacktestResult

TRADING_DAYS = 252

# Pass/fail thresholds from docs/phase-0a-plan.md (locked before any run)
PASS_SHARPE = 0.5
PASS_MAX_DD = 0.15
PASS_MIN_TRADES = 20


def compute_metrics(result: BacktestResult) -> dict:
    equity = result.equity_curve

    # Resample to daily for return computation (handles both 1h and 1d input data)
    daily_eq = equity.resample("1D").last().dropna()
    daily_ret = daily_eq.pct_change().dropna()

    ann_factor = math.sqrt(TRADING_DAYS)
    mean_ret = float(daily_ret.mean())
    std_ret = float(daily_ret.std())

    sharpe = (mean_ret / std_ret * ann_factor) if std_ret > 0 else float("nan")

    neg = daily_ret[daily_ret < 0]
    downside_std = float(neg.std()) if len(neg) > 1 else float("nan")
    sortino = (mean_ret / downside_std * ann_factor) if downside_std > 0 else float("nan")

    rolling_max = equity.cummax()
    dd_series = (equity - rolling_max) / rolling_max
    max_dd = float(dd_series.min())

    trades = result.trades
    n = len(trades)
    hit_rate = sum(1 for t in trades if t.pnl_usd > 0) / n if n > 0 else float("nan")
    gross_wins = sum(t.pnl_usd for t in trades if t.pnl_usd > 0)
    gross_losses = abs(sum(t.pnl_usd for t in trades if t.pnl_usd < 0))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("nan")

    net_return = (float(equity.iloc[-1]) - result.initial_equity) / result.initial_equity

    return {
        "net_return_pct": round(net_return * 100, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_dd_pct": round(max_dd * 100, 2),
        "n_trades": n,
        "hit_rate_pct": round(hit_rate * 100, 1) if not math.isnan(hit_rate) else float("nan"),
        "profit_factor": round(profit_factor, 3) if not math.isnan(profit_factor) else float("nan"),
    }


def pass_fail(metrics: dict, llm_cost_usd: float = 0.0) -> dict:
    """Evaluate pass/fail criteria locked in docs/phase-0a-plan.md."""
    checks = {
        "sharpe > 0.5": metrics["sharpe"] > PASS_SHARPE,
        "max_dd < 15%": metrics["max_dd_pct"] > -PASS_MAX_DD * 100,
        "n_trades >= 20": metrics["n_trades"] >= PASS_MIN_TRADES,
        "net_return > 0": metrics["net_return_pct"] > 0,
    }
    if llm_cost_usd > 0:
        net_usd = metrics["net_return_pct"] / 100 * 1_000  # assuming $1k initial equity
        checks["llm_cost <= 25% of return"] = (
            net_usd > 0 and llm_cost_usd <= 0.25 * net_usd
        )
    overall = all(checks.values())
    return {"pass": overall, "checks": checks}


def print_report(label: str, metrics: dict, pf: dict) -> None:
    verdict = "PASS ✓" if pf["pass"] else "FAIL ✗"
    print(f"\n{'='*60}")
    print(f"  {label}  —  {verdict}")
    print(f"{'='*60}")
    print(f"  Net return      : {metrics['net_return_pct']:>8.2f} %")
    print(f"  Sharpe (ann.)   : {metrics['sharpe']:>8.3f}   [threshold > 0.5]")
    print(f"  Sortino (ann.)  : {metrics['sortino']:>8.3f}")
    print(f"  Max drawdown    : {metrics['max_dd_pct']:>8.2f} %  [threshold > -15%]")
    print(f"  Trades          : {metrics['n_trades']:>8d}   [threshold >= 20]")
    print(f"  Hit rate        : {metrics['hit_rate_pct']:>8.1f} %")
    print(f"  Profit factor   : {metrics['profit_factor']:>8.3f}")
    print(f"\n  Criteria:")
    for k, v in pf["checks"].items():
        mark = "  ✓" if v else "  ✗"
        print(f"    {mark}  {k}")
    print()
