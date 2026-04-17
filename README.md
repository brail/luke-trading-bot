# luke-trading-bot

Automated crypto trading bot. Work in progress.

## Current phase: 0a — bakeoff on historical data

Deterministic baseline (momentum + volatility targeting) vs LLM-in-the-loop event-driven (Claude Sonnet 4.6), on 6 months of Hyperliquid historical OHLCV. The winning architecture proceeds to Phase 1.

## Phase plan

1. **Phase 0a** — historical bakeoff, select architecture
2. **Phase 0b** *(optional)* — multi-model comparison (GPT / Gemini / DeepSeek)
3. **Phase 1** — paper trading live, 1 week
4. **Phase 2** — real funds, cap €500
5. **Phase 3** — scale-up after validation

## Setup

```bash
uv sync
cp .env.example .env   # fill in ANTHROPIC_API_KEY
chmod 600 .env
```

## Run scripts

```bash
uv run python scripts/check_top_volumes.py
```

## Docs

- [Architecture](docs/architecture.md)
- [Risk framework](docs/risk.md)
- [Decision log](docs/decisions/)
