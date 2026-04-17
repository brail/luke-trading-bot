import math

import pandas as pd
import pytest

from bot.risk.manager import atr, chandelier_stop, circuit_breaker_hit, position_size_usd


def _s(values: list[float]) -> pd.Series:
    return pd.Series(values, dtype=float)


class TestATR:
    def test_constant_range(self) -> None:
        n = 30
        high = _s([110.0] * n)
        low = _s([90.0] * n)
        close = _s([100.0] * n)
        result = atr(high, low, close, periods=22)
        # TR for each bar: max(high-low=20, |high-prev_close|, |low-prev_close|) = 20
        assert result.dropna().round(6).eq(20.0).all()

    def test_nan_before_warmup(self) -> None:
        n = 25
        h = _s([110.0] * n)
        l = _s([90.0] * n)
        c = _s([100.0] * n)
        result = atr(h, l, c, periods=22)
        assert result.iloc[:21].isna().all()
        assert result.iloc[21:].notna().all()


class TestChandelierStop:
    def test_hh_minus_mult_atr(self) -> None:
        n = 30
        highs = _s(list(range(100, 100 + n)))  # [100, 101, ..., 129]
        atr_s = _s([5.0] * n)
        result = chandelier_stop(highs, atr_s, periods=5, mult=2.0)
        expected = highs.rolling(5, min_periods=5).max() - 10.0
        pd.testing.assert_series_equal(result, expected, check_names=False)


class TestPositionSize:
    def test_risk_limited(self) -> None:
        # atr=100, price=1000 → daily_vol_pct=0.10
        # vol_size  = (0.15/√252) * 1000 / 0.10 ≈ 94.5
        # risk_size = 0.01 * 1000 / (3 * 0.10) ≈ 33.33  ← binds
        size = position_size_usd(atr_val=100, price=1000, equity=1000)
        assert abs(size - 33.33) < 1.0

    def test_leverage_cap(self) -> None:
        # Tiny ATR → unconstrained vol/risk sizes would exceed leverage cap
        size = position_size_usd(atr_val=0.01, price=1000, equity=1000, max_leverage=3.0)
        assert size <= 3000.0

    def test_invalid_inputs_return_zero(self) -> None:
        assert position_size_usd(0.0, 1000, 1000) == 0.0
        assert position_size_usd(10.0, 0.0, 1000) == 0.0
        assert position_size_usd(10.0, 1000, 0.0) == 0.0


class TestCircuitBreaker:
    def test_daily_limit_breached(self) -> None:
        assert circuit_breaker_hit(969, 1000, 1000, 1000, daily_limit=0.03)

    def test_daily_limit_not_breached(self) -> None:
        assert not circuit_breaker_hit(971, 1000, 1000, 1000, daily_limit=0.03)

    def test_weekly_limit(self) -> None:
        # day_start = equity to avoid daily limit interfering
        assert circuit_breaker_hit(939, 939, 1000, 939, weekly_limit=0.06)
        assert not circuit_breaker_hit(941, 941, 1000, 941, weekly_limit=0.06)

    def test_monthly_limit(self) -> None:
        # day/week start = equity to isolate monthly limit
        assert circuit_breaker_hit(879, 879, 879, 1000, monthly_limit=0.12)
        assert not circuit_breaker_hit(881, 881, 881, 1000, monthly_limit=0.12)

    def test_all_limits_clean(self) -> None:
        assert not circuit_breaker_hit(1000, 1000, 1000, 1000)
