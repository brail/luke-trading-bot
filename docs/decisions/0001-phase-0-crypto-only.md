# ADR-0001: Phase 0 is crypto-only (no options / warrants)

- Date: 2026-04-17
- Status: Accepted

## Context

The project scope includes both crypto trading (on Hyperliquid) and options / warrants trading (Taleb barbell-inspired). The question is whether to address both in Phase 0 (backtest bakeoff) or crypto only.

## Decision

Phase 0 covers only crypto perpetuals on Hyperliquid. Options / warrants are deferred to Phase 1b or later.

## Rationale

| Factor | Crypto | Options |
|---|---|---|
| API access | Already available | Broker to be opened |
| Market hours | 24/7 | ~8h/day, closed weekends |
| Historical data | Free and clean | Paid or limited |
| Corporate actions | None | Dividends, splits, expiries |
| Pricing model | Spot / mark price | Greeks, IV surface, theta decay |
| Barbell strategy dependency | Separate module | Core of the strategy |

Running both simultaneously would double the technical risk at the POC stage and make it hard to attribute failure or success to a specific component.

## Consequences

- Phase 0 validates only the core architecture (data → signal → risk → execution → monitor) on a simpler market.
- The options module becomes a separate workstream that starts after Phase 1 paper trading succeeds.
- The Taleb-style OTM barbell is out of scope until then.
- If priorities invert, this ADR is superseded.

## Revisit

After Phase 1 paper trading completes successfully.
