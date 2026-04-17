# Phase 0a — Backtest bakeoff plan

- Date: 2026-04-17
- Status: Draft (awaiting user confirmation)

## Goal

Decide **empirically, with pre-committed criteria**, whether an LLM-in-the-loop trading architecture offers enough edge over a deterministic baseline to justify Phase 1 (live paper trading).

The goal is **not** to find a profitable strategy. The goal is to answer a single architectural question with numbers.

## Strategies under test

Both strategies share the same risk manager, same execution simulator, same data, same metrics. Only the signal engine differs.

### A. Deterministic baseline — Donchian breakout + ATR sizing

- **Entry long**: close breaks above 20-day highest high (Donchian channel)
- **Entry short**: disabled for Phase 0a (long-only on crypto to keep comparison simple)
- **Exit**: Chandelier Exit (`HH − 3 × ATR(22)`) or opposite signal
- **Sizing**: ATR-based, target 15% annualized portfolio volatility
- **Timeframe**: 1h candles for signals, daily rebalance of positions
- **Params sweep on TRAIN only**: entry window {10, 20, 40}, chandelier multiplier {2, 3, 4}
- **Locked before TEST**: best-performing combo on train-set Sharpe

References: Clenow *Following the Trend* (sizing), Le Beau (Chandelier Exit), Donchian 1970s turtle-trader tradition.

### B. LLM-in-the-loop event-driven — Claude Sonnet 4.6

- **Trigger events** (LLM called only when one occurs):
  1. New 20-day high or low on any of BTC / ETH / SOL
  2. Hourly move > 2σ of 20-day rolling return stdev
  3. 1h volume > 3× 20-day average volume
- **LLM input**: last 60 days OHLCV (daily resample), current positions, open PnL, risk budget remaining, event context
- **LLM output** (strict JSON schema, validated): `{action: "open_long" | "close" | "hold", size_pct_of_budget: 0..1, stop_price: float, reasoning: str}`
- **Risk manager veto**: any LLM output is clamped to the same per-trade / daily / leverage limits as strategy A. LLM does not bypass risk.
- **Model**: `claude-sonnet-4-6`
- **Prompt caching**: enabled (system prompt + historical context cached, only event delta is dynamic)

## Coin set

BTC, ETH, SOL — confirmed top-3 by volume on Hyperliquid as of 2026-04-17 (see [check_top_volumes.py output in initial commit](../scripts/check_top_volumes.py)).

## Data

- **Source**: Hyperliquid public REST API, `candleSnapshot` endpoint
- **Timeframe**: 1h primary (~4320 candles / 6 months, single request per coin)
- **Period total**: 2025-10-17 → 2026-04-17 (6 months)
- **Train set**: 2025-10-17 → 2026-02-17 (4 months, ~122 days)
- **Test set (OOS)**: 2026-02-17 → 2026-04-17 (2 months, ~60 days)
- Storage: Parquet files under `data/cache/` (gitignored)

**Discipline**: params for strategy A and the prompt for strategy B are **frozen** before touching the test set. No iteration on the test set. If a bug is found in test-set code, we fix the bug and re-run, but we do not tune strategy params.

## Risk framework (applies to both)

Per [docs/risk.md](risk.md):
- Max risk per trade: 1% equity (enforced at sizing)
- Daily kill-switch: 3% drawdown → flat positions, no new orders same UTC day
- Max leverage: 3x
- Starting equity: $1,000 (notional, for cleaner PnL math)

## Metrics (computed on TEST set only)

| Metric | Formula / note |
|---|---|
| Net return | Cumulative PnL after fees |
| Sharpe (ann.) | Mean / std of daily returns × √365 |
| Sortino (ann.) | Mean / std of negative daily returns × √365 |
| Max drawdown | Peak-to-trough, as % of peak equity |
| Hit rate | % of trades with PnL > 0 |
| Profit factor | Gross wins / gross losses |
| # trades | Total opens |
| Avg holding period | Mean bars in trade |
| Turnover | Annualized |
| LLM cost (B only) | Total $ spent on Anthropic API |
| LLM cost ratio (B only) | LLM cost / net return (if net return > 0) |

Trading cost assumption: **10 bps per trade** (2× Hyperliquid taker fee of ~4-5 bps, conservative for POC).

## Pass / fail criteria (committed before any run)

A strategy **passes** if it satisfies **all** of the following on the test set:

1. Sharpe > 0.5
2. Max drawdown < 15%
3. Number of trades ≥ 20 (minimum statistical sample)
4. Net return > 0 after trading costs
5. *(Strategy B only)* LLM cost ≤ 25% of net return

**Phase 0a outcome:**

- **Strategy A passes, B fails** → proceed to Phase 1 with deterministic baseline only. LLM architecture parked.
- **Strategy B passes, A fails** → red flag (LLM found edge where simple rules did not?). Deep review before trusting it. Possibly Phase 0b to verify across more models.
- **Both pass** → pick whichever has better risk-adjusted return (Sharpe) for Phase 1, document loser in ADR.
- **Both fail** → Phase 0a is negative. We do not proceed to Phase 1. Options: (i) revise strategies, (ii) test different regime / timeframe, (iii) pivot to Taleb-style options barbell on a different workstream.

## LLM budget

Estimate for strategy B:
- ~10 trigger events / day × 180 days = 1800 LLM calls
- Per call: ~2000 input tokens (system + context) + 500 output tokens
- Sonnet 4.6 pricing: $3 / M input, $15 / M output
- Raw: 3.6 × $3 + 0.9 × $15 = **$24**
- With prompt caching (system prompt reused): ~$15-20
- Buffer for prompt iteration on TRAIN set: +50%

**Hard cap: $50 total.** Enforced in code by checking cumulative cost before each call; abort backtest if exceeded (flag in the report).

## Implementation milestones

Each milestone ends with a working commit pushed to `main`. User reviews before the next milestone starts.

| # | Milestone | Output |
|---|---|---|
| M1 | Historical data loader | `bot/data/historical.py`, cached Parquet files, unit tests |
| M2 | Backtest harness skeleton | `backtest/harness.py`, paper execution simulator, equity curve computation |
| M3 | Risk manager | `bot/risk/manager.py`, position sizing, stops, circuit breakers, unit tests |
| M4 | Strategy A (baseline) | `bot/strategies/donchian_atr.py`, param sweep on train, lock best params |
| M5 | Metrics module | `backtest/metrics.py`, full table + plots |
| M6 | First OOS run of A | `runs/phase0a_A.json` + markdown report |
| M7 | Strategy B (LLM) | `bot/strategies/llm_eventdriven.py`, prompt caching, JSON schema validation |
| M8 | LLM cost tracker | Instrumented during backtest, hard cap enforced |
| M9 | OOS run of B | `runs/phase0a_B.json` + markdown report |
| M10 | Final bakeoff report | `runs/phase0a_final.md`, pass/fail verdict per strategy, ADR-0002 |
| M11 | Go/no-go review | User reads ADR-0002, accepts or rejects, decides Phase 1 architecture |

## Definition of done for Phase 0a

All of:
- [ ] Both strategies implemented and fully tested
- [ ] Same risk manager wired to both (verified by tests)
- [ ] Reproducibility: running `uv run python backtest/run_phase0a.py` twice produces identical results (modulo LLM non-determinism, which is logged separately with seed info)
- [ ] `runs/phase0a_final.md` written with pass/fail per strategy
- [ ] ADR-0002 committed documenting the verdict and the chosen architecture for Phase 1
- [ ] User signs off on go/no-go

## Out of scope for Phase 0a

- Live execution / Hyperliquid SDK integration (Phase 1)
- Telegram monitoring (Phase 1)
- Multi-model bakeoff (Phase 0b, only if 0a passes)
- Options / warrants (Phase 1b or later per ADR-0001)
- Walk-forward analysis (Phase 0b)
- Hybrid strategies (Phase 0b or Phase 1 refinement)
