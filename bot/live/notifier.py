"""Telegram notifier for paper trading events.

Reads TELEGRAM_TOKEN and TELEGRAM_CHAT_ID from environment.
Silently skips if credentials are missing (allows running without Telegram).
"""

from __future__ import annotations

import os
import urllib.request
import urllib.parse
import json


def _send(text: str) -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        print(f"  [Telegram] send failed: {exc}")


def notify_trade_open(coin: str, side: str, price: float, stop: float, size_usd: float) -> None:
    emoji = "🟢" if side == "long" else "🔴"
    _send(
        f"{emoji} <b>OPEN {side.upper()} {coin}</b>\n"
        f"Entry: ${price:.2f}\n"
        f"Stop:  ${stop:.2f}\n"
        f"Size:  ${size_usd:.2f}"
    )


def notify_trade_close(coin: str, side: str, entry: float, exit_price: float, pnl: float, reason: str) -> None:
    emoji = "✅" if pnl >= 0 else "❌"
    _send(
        f"{emoji} <b>CLOSE {side.upper()} {coin}</b>\n"
        f"Entry: ${entry:.2f} → Exit: ${exit_price:.2f}\n"
        f"P&L:   ${pnl:+.2f}  ({reason})"
    )


def notify_summary(equity: float, initial: float, n_trades: int, open_positions: dict) -> None:
    pnl_pct = (equity / initial - 1) * 100
    pos_str = ", ".join(f"{c} {p['side'].upper()}" for c, p in open_positions.items()) or "none"
    _send(
        f"📊 <b>Paper trader — 4h update</b>\n"
        f"Equity: ${equity:.2f}  ({pnl_pct:+.1f}%)\n"
        f"Trades: {n_trades} closed\n"
        f"Open:   {pos_str}"
    )
