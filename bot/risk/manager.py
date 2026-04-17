from __future__ import annotations

import math

import pandas as pd

TRADING_DAYS = 252


def atr(high: pd.Series, low: pd.Series, close: pd.Series, periods: int = 22) -> pd.Series:
    """Average True Range over *periods* bars."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.rolling(periods, min_periods=periods).mean()


def chandelier_stop(
    high: pd.Series, atr_series: pd.Series, periods: int = 22, mult: float = 3.0
) -> pd.Series:
    """Long trailing stop: rolling highest-high over *periods* minus *mult* × ATR."""
    return high.rolling(periods, min_periods=periods).max() - mult * atr_series


def chandelier_stop_short(
    low: pd.Series, atr_series: pd.Series, periods: int = 22, mult: float = 3.0
) -> pd.Series:
    """Short trailing stop: rolling lowest-low over *periods* plus *mult* × ATR."""
    return low.rolling(periods, min_periods=periods).min() + mult * atr_series


def position_size_usd(
    atr_val: float,
    price: float,
    equity: float,
    max_risk_pct: float = 0.01,
    target_ann_vol: float = 0.15,
    max_leverage: float = 3.0,
    stop_mult: float = 3.0,
) -> float:
    """Return the smaller of vol-targeting size and max-risk-at-stop size, capped at leverage."""
    if atr_val <= 0 or price <= 0 or equity <= 0:
        return 0.0
    daily_vol_pct = atr_val / price
    # size s.t. position daily-vol contribution = target_ann_vol / sqrt(TRADING_DAYS)
    vol_size = (target_ann_vol / math.sqrt(TRADING_DAYS)) * equity / daily_vol_pct
    # size s.t. loss if stop hit = max_risk_pct * equity
    risk_size = max_risk_pct * equity / (stop_mult * daily_vol_pct)
    return float(min(vol_size, risk_size, max_leverage * equity))


def circuit_breaker_hit(
    equity: float,
    day_start: float,
    week_start: float,
    month_start: float,
    daily_limit: float = 0.03,
    weekly_limit: float = 0.06,
    monthly_limit: float = 0.12,
) -> bool:
    """Return True if any drawdown threshold is breached (trading should halt)."""
    return (
        equity < day_start * (1 - daily_limit)
        or equity < week_start * (1 - weekly_limit)
        or equity < month_start * (1 - monthly_limit)
    )
