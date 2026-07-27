"""
Tests for the pure risk-metric functions.
"""

import numpy as np
import pandas as pd
import pytest

from src.ml import risk_metrics


def _series(values):
    """Helper: a date-indexed price series."""
    idx = pd.date_range("2025-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=idx, dtype="float64")


class TestDailyReturns:
    def test_computes_simple_returns(self):
        """100 -> 101 is +1%, 100 -> 103 is +3%. Hand-checkable."""
        prices = _series([100.0, 101.0, 102.0, 100.0, 103.0])
        rets = risk_metrics.daily_returns(prices)

        assert len(rets) == 4  # first value has no prior day, so it's dropped
        assert rets.iloc[0] == pytest.approx(0.01)
        assert rets.iloc[-1] == pytest.approx(0.03)

    def test_empty_on_insufficient_data(self):
        """A single price can't produce a return."""
        assert risk_metrics.daily_returns(_series([100.0])).empty
        assert risk_metrics.daily_returns(None).empty


class TestAnnualizedVolatility:
    def test_scales_by_sqrt_trading_days(self):
        """Annualised vol = daily stdev * sqrt(252)."""
        rets = pd.Series([0.01, -0.01, 0.02, -0.02, 0.015])
        expected = rets.std(ddof=1) * np.sqrt(risk_metrics.TRADING_DAYS_PER_YEAR)

        assert risk_metrics.annualized_volatility(rets) == pytest.approx(expected)

    def test_none_when_too_few_points(self):
        assert risk_metrics.annualized_volatility(pd.Series([0.01])) is None
        assert risk_metrics.annualized_volatility(None) is None


class TestBeta:
    def test_beta_against_itself_is_exactly_one(self):
        """cov(x, x) / var(x) == 1 by definition.

        This is the single most valuable assertion in the suite: it's a
        mathematical certainty, so any deviation means the formula is wrong.
        """
        rets = risk_metrics.daily_returns(_series([100, 102, 101, 105, 103, 107]))

        assert risk_metrics.beta(rets, rets) == pytest.approx(1.0)

    def test_none_against_flat_benchmark(self):
        """A benchmark that never moves has zero variance, so beta is undefined.

        Guards against a divide-by-zero producing inf instead of an honest None.
        """
        rets = risk_metrics.daily_returns(_series([100, 102, 101, 105]))
        flat = pd.Series([0.0] * len(rets), index=rets.index)

        assert risk_metrics.beta(rets, flat) is None

    def test_aligns_on_shared_dates_only(self):
        """ASX and US markets have different holidays, so the two series must be
        inner-joined on date. Mismatched rows would silently corrupt the result —
        this is the class of bug that produced beta 0.03 for IVV.AX.
        """
        asset = pd.Series(
            [0.01, 0.02, -0.01],
            index=pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
        )
        # Benchmark is missing Jan 3 (a holiday on that exchange).
        bench = pd.Series(
            [0.01, -0.01],
            index=pd.to_datetime(["2025-01-02", "2025-01-06"]),
        )

        # Only two overlapping days — enough to compute, and it must not raise.
        assert risk_metrics.beta(asset, bench) is not None

    def test_none_on_no_overlap(self):
        a = pd.Series([0.01, 0.02], index=pd.to_datetime(["2025-01-02", "2025-01-03"]))
        b = pd.Series([0.01, 0.02], index=pd.to_datetime(["2025-06-02", "2025-06-03"]))

        assert risk_metrics.beta(a, b) is None


class TestWeeklyReturns:
    def test_resamples_to_roughly_one_fifth(self):
        """Weekly resampling exists to fix cross-market timezone misalignment.
        50 business days should collapse to roughly 10 weekly periods."""
        prices = _series(np.linspace(100, 120, 50))
        weekly = risk_metrics.weekly_returns(prices)

        assert 8 <= len(weekly) <= 11

    def test_empty_on_insufficient_data(self):
        assert risk_metrics.weekly_returns(_series([100.0])).empty


class TestSharpeRatio:
    def test_none_when_volatility_is_zero(self):
        """Constant returns mean zero volatility, so the ratio is undefined."""
        flat = pd.Series([0.001] * 10)

        assert risk_metrics.sharpe_ratio(flat, risk_free_annual=0.04) is None

    def test_higher_return_gives_higher_sharpe(self):
        """Directional sanity: same volatility, better returns, better Sharpe."""
        rng = np.random.default_rng(0)
        noise = rng.normal(0, 0.01, 200)
        modest = pd.Series(noise + 0.0002)
        strong = pd.Series(noise + 0.0010)

        assert (risk_metrics.sharpe_ratio(strong, 0.04)
                > risk_metrics.sharpe_ratio(modest, 0.04))


class TestRiskFreeRate:
    def test_known_markets_have_their_own_rate(self):
        assert risk_metrics.risk_free_for_market("AU") == risk_metrics.RISK_FREE_RATES["AU"]
        assert risk_metrics.risk_free_for_market("US") == risk_metrics.RISK_FREE_RATES["US"]

    def test_unknown_market_falls_back(self):
        assert risk_metrics.risk_free_for_market("MARS") == risk_metrics.DEFAULT_RISK_FREE