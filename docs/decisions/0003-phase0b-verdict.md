# ADR-0003: Phase 0b verdict — strategy passes, proceed to Phase 1

- Date: 2026-04-17
- Status: Accepted

## Results

| Metric | Value | Pass threshold |
|---|---|---|
| Net return (OOS) | +41.31% | > 0% |
| Sharpe (ann.) | 0.687 | > 0.5 |
| Sortino (ann.) | 1.193 | — |
| Max drawdown | −11.32% | > −15% |
| Trades | 347 | ≥ 20 |
| Hit rate | 37.2% | — |
| Profit factor | 1.282 | — |

**All four pass criteria met.**

## Setup

- Data: Binance spot 4h OHLCV, BTC/ETH/SOL, 2020-01-01 → 2026-01-01
- Train: 2020-01-01 → 2023-01-01 (3 years, 3 full bull/bear cycles)
- Test:  2023-01-01 → 2026-01-01 (3 years, includes 2025-2026 bear)
- Strategy: Donchian ATR bidirectional (long + short)
- Best params (train): `entry_window=60` (10 days), `chandelier_mult=3.0`
- Train Sharpe: 0.771 → Test Sharpe: 0.687 — good generalisation, no overfit signal

## Root causes fixed vs Phase 0a

1. **Long-only removed** — short positions captured the 2025-2026 downtrend
2. **More data** — 6 years vs 6 months; multiple regime cycles covered
3. **4h bars** — 347 trades in 3 years (vs 8 in 60 days); statistically credible

## Decisions not taken

- **LLM overlay skipped** — deterministic baseline already passes; LLM adds cost and
  complexity before live validation. Revisit after Phase 1 if needed.
- **Options/Taleb barbell deferred** — pending Phase 1 paper trading results.

## Decision: proceed to Phase 1 — paper trading

- Paper trade for ≥ 1 week on Hyperliquid real-time data
- Initial virtual equity: $1,000
- Strategy params locked: `entry_window=60`, `chandelier_mult=3.0`
- Coins: BTC, ETH, SOL perpetuals
- Run every 4h (cron or manual)
- Pass criteria for Phase 2 (real funds): Sharpe > 0 over the paper period,
  no circuit breaker triggered, execution model validated

## Supersedes

ADR-0002 option A+B chosen and executed.
