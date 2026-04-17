# Risk framework

Concrete limits for Phase 0a (backtest) and Phase 1+ (live).

| Limit | Value | Source / rationale |
|---|---|---|
| Max risk per trade | 1% of equity | Van Tharp — fixed fractional standard |
| Daily drawdown kill-switch | 3% | CTA industry standard |
| Weekly drawdown review | 6% | Retail quant consensus |
| Monthly hard stop | 12% | Forces manual review or shutdown |
| Max effective leverage (BTC / ETH) | 3x | Retail disciplined cap |
| Max effective leverage (SOL, alt liquids) | 3x (Phase 0 conservative) | Revisit after Phase 0a |
| Position sizing method | ATR-based, target 15% annualized volatility | Clenow, *Following the Trend* |
| Trailing stop | Chandelier Exit: `HH − 3 × ATR(22)` | Le Beau — standard in trend systems |

## Circuit breakers

- **Daily**: if cumulative daily PnL < −3% of day-start equity → flat all positions, no new orders until next UTC day.
- **Weekly**: if week PnL < −6% → strategy suspended, manual review before resume.
- **Monthly**: if month PnL < −12% → full shutdown, strategy re-evaluation.

## Leverage policy

Configured leverage on Hyperliquid is capped at 3x even though the exchange allows up to ~50x. Position size is driven by **risk at stop distance** (1% of equity), not by leverage. Leverage is only a ceiling.

## Review cadence

- **Daily**: automated log of risk-metric breaches.
- **Weekly**: manual review of Sharpe, Sortino, max DD, hit rate, turnover.
- **Monthly**: full strategy review, possible adjustment of limits.

## Sources

- Van Tharp, *Trade Your Way to Financial Freedom* — position sizing, R-multiples
- Ralph Vince, *The Mathematics of Money Management* — fractional Kelly
- Andreas Clenow, *Following the Trend* — ATR-based sizing, volatility targeting
- Chuck Le Beau — Chandelier Exit
- Ernie Chan, *Algorithmic Trading* — validation, regime considerations
