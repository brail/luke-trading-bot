# ADR-0002: Phase 0a verdict — both strategies fail, do not proceed to Phase 1

- Date: 2026-04-17
- Status: Accepted

## Results

| Metric | Strategy A (Donchian ATR) | Strategy B (LLM event-driven) | Pass threshold |
|---|---|---|---|
| Net return | −1.79% | −1.85% | > 0% |
| Sharpe (ann.) | −1.720 | −3.682 | > 0.5 |
| Max drawdown | −3.55% | −1.85% | > −15% |
| Trades (test) | 8 | 4 | ≥ 20 |
| Hit rate | 37.5% | 0.0% | — |
| LLM cost | — | $0.11 (13 calls) | ≤ 25% of return |

Both strategies **fail** on Sharpe, trade count, and net return. Only max drawdown passes.

## Root causes

**1. Adverse market regime.** The test period (Feb–Apr 2026) was a downtrend for BTC/ETH/SOL. Both strategies are long-only with a bullish momentum bias. Long-only strategies have no mechanism to profit in sustained bear markets.

**2. Insufficient trade count.** Strategy A: 8 trades in 60 days × 3 coins. Strategy B: 4 trades (only 13 LLM events fired). Far below the minimum of 20 required for statistical credibility. The strategies simply did not generate enough signals.

**3. Training period also negative.** On the 4-month train set, the best Sharpe for Strategy A was −0.79 across all 9 param combinations. This means the strategies had no edge even during "development", ruling out simple test-set bad luck.

**4. LLM did not add signal.** Strategy B achieved 0% hit rate (all 4 trades lost). The LLM operated in the same adverse regime and generated entries on down-trending assets.

## What this is NOT

- This is not evidence that automated crypto trading is impossible
- This is not evidence that LLMs cannot trade
- This is not evidence that Donchian breakout never works

It is evidence that **long-only momentum strategies underperform in bear/sideways regimes**, and that **6 months of data in one regime is insufficient to evaluate an architecture**

## Decision: do not proceed to Phase 1

Per the pre-committed criteria in docs/phase-0a-plan.md, Phase 0a is negative. Real funds are not deployed.

## Options going forward (not yet decided)

**Option A: Extend historical data range**
- Use CCXT + Binance to fetch 2020–2025 data (includes bull and bear cycles)
- Re-run bakeoff on 3+ years → more statistically meaningful results
- Cost: ~1 week of work, cheap data
- Trade-off: Binance data ≠ Hyperliquid data (funding, liquidity differ slightly)

**Option B: Change strategy type — add short capability**
- Allow short positions on Donchian breakdowns
- Long-short trend following is the canonical Clenow approach
- Trade-off: more complex risk management; need to revisit leverage limits

**Option C: Pivot to long-volatility (Taleb barbell)**
- Buy OTM options on crypto (Deribit) during low-vol periods
- Profit from explosive moves regardless of direction
- Aligned with Taleb philosophy
- Trade-off: requires opening Deribit account; options pricing model adds complexity; loses slowly until a tail event

**Option D: Hybrid — Options barbell + momentum**
- 80% in cash/stablecoins, 20% in Donchian long-short on top 3 perps
- Momentum component gives activity; barbell gives asymmetric payoff
- Most aligned with original project goals
- Trade-off: highest implementation complexity

## Revisit

Once the user decides on an option, this ADR is superseded by ADR-0003.
