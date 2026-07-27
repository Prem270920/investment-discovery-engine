"""
One test, guarding the property the forecasting feature ethically depends on:
the confidence band must widen with the horizon.

A projection whose uncertainty stays flat tells a beginner that a 30-day
forecast is as reliable as a 1-day one. That's the opposite of what this
feature exists to communicate — and an early version of the returns path did
exactly that, because it applied single-step uncertainty instead of
accumulating it.

Marked slow: it fits real ARIMA models.
"""

import numpy as np
import pandas as pd
import pytest

from src.ml.forecasting import forecast_asset


@pytest.mark.slow
def test_confidence_band_widens_with_horizon():
    rng = np.random.default_rng(42)
    n = 250
    trend = np.linspace(100, 130, n)
    noise = rng.normal(0, 2, n).cumsum() * 0.3
    prices = pd.Series(
        np.maximum(trend + noise, 1.0),
        index=pd.date_range("2025-01-01", periods=n, freq="B"),
    )

    result = forecast_asset(prices)
    assert result is not None, "engine failed to fit a well-behaved series"

    first_day = result["upper"][0] - result["lower"][0]
    last_day = result["upper"][-1] - result["lower"][-1]

    assert last_day > first_day * 1.5, (
        f"band barely widened ({first_day:.2f} -> {last_day:.2f}); "
        "uncertainty must compound over the horizon"
    )


@pytest.mark.slow
def test_short_series_returns_none_rather_than_guessing():
    """Not enough history to fit and backtest honestly, so the engine should return None rather than a guess."""
    prices = pd.Series(
        np.linspace(100, 105, 20),
        index=pd.date_range("2025-01-01", periods=20, freq="B"),
    )

    assert forecast_asset(prices) is None