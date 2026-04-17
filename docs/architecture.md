# Architecture

## Components

```
┌─ Data feeds          → Hyperliquid public REST/WS, historical OHLCV
│
├─ Signal engine       → Strategy implementations (deterministic, LLM, hybrid)
│
├─ Risk manager        → Position sizing, stops, circuit breakers
│
├─ Execution layer     → Hyperliquid SDK (live), paper adapter (POC)
│
├─ State store         → SQLite: trades, positions, PnL
│
└─ Monitoring          → Telegram alerts, structured logging
```

The same components are used by both the backtest harness (fed with historical data) and the live runner (fed with real-time data). This enforces behavioural parity and prevents lookahead bias.

## Directory layout

- `bot/` — production code (data, strategies, risk, execution, state, monitoring)
- `backtest/` — backtest harness and metrics (to be added)
- `scripts/` — one-off utilities
- `docs/` — documentation and decision log
- `tests/` — unit and integration tests (to be added)

## Status

Phase 0a. Only the Hyperliquid read-only client exists so far.
