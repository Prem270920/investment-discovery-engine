"""
Tests for the shared RMSE-as-percent-of-price score.

The expected values are worked out by hand so a change to the formula shows
up as a failure here, not as a quiet shift in stored backtest errors.
"""

import numpy as np
import pandas as pd
import pytest

from src.ml.forecast_metrics import rmse_pct_of_price


def test_known_arrays_give_exact_value():
    # Misses of -3, +4, 0, 0: mean square 25/4, RMSE 2.5, mean price 50.
    actual_prices = [40.0, 60.0, 45.0, 55.0]
    predicted_prices = [43.0, 56.0, 45.0, 55.0]
    assert rmse_pct_of_price(actual_prices, predicted_prices) == 5.0


def test_symmetric_misses_around_flat_price():
    # Every day misses by exactly 2 on a price of 100.
    assert rmse_pct_of_price([100.0] * 4, [102.0, 98.0, 102.0, 98.0]) == 2.0


def test_perfect_forecast_scores_zero():
    assert rmse_pct_of_price([10.0, 11.0, 12.0], [10.0, 11.0, 12.0]) == 0.0


def test_matches_the_formula_arima_used_before_extraction():
    # Same arithmetic as the old private helper in forecasting.py, so moving
    # it cannot have changed any stored ARIMA error.
    rng = np.random.default_rng(7)
    actual_prices = rng.uniform(5, 500, 30)
    predicted_prices = actual_prices + rng.normal(0, 3, 30)
    old_style = (
        float(np.sqrt(np.mean((actual_prices - predicted_prices) ** 2)))
        / (float(np.mean(actual_prices)) or 1.0)
    ) * 100.0
    assert rmse_pct_of_price(actual_prices, predicted_prices) == old_style


def test_accepts_pandas_series():
    actual_prices = pd.Series([40.0, 60.0, 45.0, 55.0], index=[3, 7, 9, 11])
    assert rmse_pct_of_price(actual_prices, np.array([43.0, 56.0, 45.0, 55.0])) == 5.0


def test_zero_mean_price_falls_back_to_raw_rmse():
    # RMSE is 1.0, and with no price to scale by it is reported as 1.0 * 100.
    assert rmse_pct_of_price([1.0, -1.0], [0.0, 0.0]) == 100.0


def test_mismatched_lengths_are_refused():
    with pytest.raises(ValueError):
        rmse_pct_of_price([1.0, 2.0, 3.0], [1.0, 2.0])


def test_empty_window_is_refused():
    with pytest.raises(ValueError):
        rmse_pct_of_price([], [])
