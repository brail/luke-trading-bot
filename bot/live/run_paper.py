"""Phase 1 — paper trading entry point.

Run every 4h (manually or via cron). Params are locked from Phase 0b best train result.

Usage:
    uv run python bot/live/run_paper.py

Cron (every 4h, 5 min after bar close):
    5 0,4,8,12,16,20 * * * cd /path/to/trading && uv run python bot/live/run_paper.py >> logs/paper.log 2>&1
"""

from bot.live.paper_trader import PaperTrader

# Params locked from Phase 0b param sweep (best train Sharpe = 0.771)
ENTRY_WINDOW    = 60
CHANDELIER_MULT = 3.0
STATE_PATH      = "state/paper_state.json"


if __name__ == "__main__":
    trader = PaperTrader(
        state_path=STATE_PATH,
        entry_window=ENTRY_WINDOW,
        chandelier_mult=CHANDELIER_MULT,
    )
    trader.run()
