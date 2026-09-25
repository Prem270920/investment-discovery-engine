"""
Tests for the GRU windowing and split.

The leakage checks build prices from returns that each carry their own
position (the k-th return is 0.0001 * (k + 1)), so after unscaling any value
in a window says exactly which day it came from.
"""

import numpy as np
import pandas as pd
import pytest

from src.ml.forecasting import BACKTEST_DAYS
from src.ml.sequence_windows import (
    MIN_PRICES,
    WINDOW_LENGTH,
    build_sequence_windows,
    simple_returns,
)

RETURN_STEP = 0.0001


def _prices_from_returns(daily_returns, start_price=100.0):
    return start_price * np.cumprod(np.concatenate([[1.0], 1.0 + np.asarray(daily_returns)]))


def _positional_prices(price_count):
    positional_returns = RETURN_STEP * np.arange(1, price_count)
    return _prices_from_returns(positional_returns)


def _positions(scaler, scaled_values):
    raw_returns = scaler.unscale(np.asarray(scaled_values, dtype=np.float64))
    return np.rint(raw_returns / RETURN_STEP).astype(int) - 1


def test_window_shapes_for_known_length():
    # 251 prices -> 250 returns -> 220 before the holdout -> 190 windows,
    # of which the last 20 percent (38) are validation.
    windows = build_sequence_windows([_positional_prices(251)])
    assert windows.train_inputs.shape == (152, WINDOW_LENGTH, 1)
    assert windows.train_targets.shape == (152,)
    assert windows.val_inputs.shape == (38, WINDOW_LENGTH, 1)
    assert windows.val_targets.shape == (38,)
    assert windows.holdout_seeds[0].shape == (WINDOW_LENGTH, 1)
    assert windows.holdout_returns[0].shape == (BACKTEST_DAYS,)
    assert windows.train_inputs.dtype == np.float32


def test_no_holdout_value_reaches_training_or_validation():
    windows = build_sequence_windows([_positional_prices(251)])
    first_holdout_position = 250 - BACKTEST_DAYS

    holdout_positions = set(_positions(windows.scaler, windows.scaler.scale(windows.holdout_returns[0])))
    assert holdout_positions == set(range(first_holdout_position, 250))

    for window_array in (windows.train_inputs, windows.train_targets,
                         windows.val_inputs, windows.val_targets, windows.holdout_seeds[0]):
        seen_positions = set(_positions(windows.scaler, window_array).ravel())
        assert seen_positions.isdisjoint(holdout_positions)


def test_targets_follow_their_inputs_and_stop_right_before_holdout():
    windows = build_sequence_windows([_positional_prices(251)])
    train_target_positions = _positions(windows.scaler, windows.train_targets)
    val_target_positions = _positions(windows.scaler, windows.val_targets)

    assert list(train_target_positions) == list(range(WINDOW_LENGTH, WINDOW_LENGTH + 152))
    assert list(val_target_positions) == list(range(WINDOW_LENGTH + 152, 220))

    # Each window is the 30 days immediately before its target.
    first_window = _positions(windows.scaler, windows.train_inputs[0, :, 0])
    assert list(first_window) == list(range(0, WINDOW_LENGTH))
    last_val_window = _positions(windows.scaler, windows.val_inputs[-1, :, 0])
    assert list(last_val_window) == list(range(219 - WINDOW_LENGTH, 219))


def test_holdout_seed_is_last_window_before_holdout():
    windows = build_sequence_windows([_positional_prices(251)])
    seed_positions = _positions(windows.scaler, windows.holdout_seeds[0][:, 0])
    assert list(seed_positions) == list(range(220 - WINDOW_LENGTH, 220))


def test_scaler_statistics_come_from_training_returns_only():
    # Validation and holdout returns are wildly different from training ones,
    # so any leak into the statistics would move them a long way.
    rng = np.random.default_rng(3)
    training_part = rng.normal(0.001, 0.01, WINDOW_LENGTH + 152)
    validation_part = rng.normal(0.2, 0.05, 38)
    holdout_part = rng.normal(-0.3, 0.05, BACKTEST_DAYS)
    all_returns = np.concatenate([training_part, validation_part, holdout_part])

    windows = build_sequence_windows([_prices_from_returns(all_returns)])
    returns_seen_by_pipeline = simple_returns(_prices_from_returns(all_returns))
    training_slice = returns_seen_by_pipeline[:WINDOW_LENGTH + 152]

    assert windows.scaler.mean == pytest.approx(np.mean(training_slice), abs=1e-15)
    assert windows.scaler.std == pytest.approx(np.std(training_slice), abs=1e-15)
    assert windows.scaler.mean == pytest.approx(0.001, abs=0.003)
    # Checked against each leak separately; with both included the positive
    # validation drift and negative holdout drift would partly cancel.
    with_validation = returns_seen_by_pipeline[:WINDOW_LENGTH + 152 + 38]
    with_holdout = np.concatenate([training_slice, returns_seen_by_pipeline[-BACKTEST_DAYS:]])
    assert windows.scaler.mean != pytest.approx(np.mean(with_validation), abs=0.01)
    assert windows.scaler.mean != pytest.approx(np.mean(with_holdout), abs=0.01)
    assert windows.scaler.std != pytest.approx(np.std(with_validation), abs=0.01)

    scaled_training = windows.scaler.scale(training_slice)
    assert np.mean(scaled_training) == pytest.approx(0.0, abs=1e-12)
    assert np.std(scaled_training) == pytest.approx(1.0, abs=1e-12)


def test_two_series_combine_their_window_counts():
    # 251 prices give 152 train + 38 validation; 151 prices give 72 + 18.
    windows = build_sequence_windows([_positional_prices(251), _positional_prices(151)])
    assert windows.train_inputs.shape == (152 + 72, WINDOW_LENGTH, 1)
    assert windows.val_inputs.shape == (38 + 18, WINDOW_LENGTH, 1)
    assert len(windows.holdout_seeds) == 2
    assert len(windows.holdout_returns) == 2


def test_return_definition_matches_arima_returns_model():
    closes = pd.Series([100.0, 101.0, np.nan, 99.5, 102.0, 102.0, 98.0])
    # forecast_asset drops missing closes, then the returns model calls
    # pct_change().dropna() on them.
    arima_style = closes.dropna().pct_change().dropna().to_numpy()
    assert np.array_equal(simple_returns(closes), arima_style)


def test_holdout_matches_arima_backtest_cut():
    prices = _positional_prices(251)
    windows = build_sequence_windows([prices])
    # ARIMA scores on prices[-30:], so the first holdout return is the move
    # from the last training price into the first holdout price.
    assert windows.holdout_returns[0][0] == pytest.approx(prices[-BACKTEST_DAYS] / prices[-BACKTEST_DAYS - 1] - 1)


def test_shortest_allowed_series_gives_one_window_each():
    windows = build_sequence_windows([_positional_prices(MIN_PRICES)])
    assert len(windows.train_targets) == 1
    assert len(windows.val_targets) == 1


def test_too_short_series_is_refused():
    with pytest.raises(ValueError):
        build_sequence_windows([_positional_prices(MIN_PRICES - 1)])


def test_empty_list_is_refused():
    with pytest.raises(ValueError):
        build_sequence_windows([])
