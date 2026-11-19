"""
Turns price histories into supervised windows for a sequence model (the GRU)

The split mirrors the ARIMA backtest so the head to head is fair:
  * holdout    : the last BACKTEST_DAYS price bars, the same window ARIMA is
                 scored on. Nothing from it reaches training, validation or
                 the scaler. A forward model passes holdout_days=0 to train
                 on every bar.
  * validation : the last 20 percent of the remaining windows per series,
                 kept for early stopping.
  * training   : everything before that.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.ml.forecasting import BACKTEST_DAYS

WINDOW_LENGTH = 30
VALIDATION_PERCENT = 20


def min_prices_for(holdout_days: int) -> int:
    """Smallest series that yields at least one training and one validation
    window: one leading bar lost to pct_change, the holdout, the first
    window's inputs, and a target each for train and validation."""
    return 1 + holdout_days + WINDOW_LENGTH + 2


MIN_PRICES = min_prices_for(BACKTEST_DAYS)


@dataclass(frozen=True)
class ReturnScaler:
    """Standardises returns with statistics fitted on training returns only."""
    mean: float
    std: float

    def scale(self, raw_returns):
        return (np.asarray(raw_returns, dtype=float) - self.mean) / self.std

    def unscale(self, scaled_returns):
        return np.asarray(scaled_returns, dtype=float) * self.std + self.mean


@dataclass(frozen=True)
class SequenceWindows:
    """Model-ready arrays. Inputs are shaped (samples, WINDOW_LENGTH, 1) to
    match a batch_first GRU with a single feature."""
    train_inputs: np.ndarray
    train_targets: np.ndarray
    val_inputs: np.ndarray
    val_targets: np.ndarray
    scaler: ReturnScaler
    # Per series, the last scaled window before the holdout: the input the
    # model rolls forward from to forecast the holdout days.
    holdout_seeds: list[np.ndarray]
    # Per series, the raw holdout returns, kept only for scoring.
    holdout_returns: list[np.ndarray]


def simple_returns(prices) -> np.ndarray:
    """Daily simple returns, defined exactly as the ARIMA returns model does:
    pct_change on the closes with the leading NaN dropped."""
    closes = pd.Series(np.asarray(prices, dtype=float)).dropna()
    return closes.pct_change().dropna().to_numpy()


def _stack_windows(return_run: np.ndarray, window_count: int, first_target: int):
    """Windows whose targets are return_run[first_target : first_target + window_count]."""
    inputs = np.stack([
        return_run[target_pos - WINDOW_LENGTH:target_pos]
        for target_pos in range(first_target, first_target + window_count)
    ])
    targets = return_run[first_target:first_target + window_count]
    return inputs, targets


def build_sequence_windows(price_series_list, holdout_days: int = BACKTEST_DAYS) -> SequenceWindows:
    """Build scaled train and validation windows from one or more price series.

    holdout_days defaults to the ARIMA backtest window. Pass 0 for a forward
    model: every return is then used and the seed is the latest window.
    """
    if not price_series_list:
        raise ValueError("need at least one price series")
    if holdout_days < 0:
        raise ValueError(f"holdout_days must be >= 0, got {holdout_days}")
    min_prices = min_prices_for(holdout_days)

    split_plans = []
    for position, prices in enumerate(price_series_list):
        series_returns = simple_returns(prices)
        if len(series_returns) + 1 < min_prices:
            raise ValueError(
                f"series {position} has {len(series_returns) + 1} prices, "
                f"need at least {min_prices}"
            )
        # Cutting in return space at -holdout_days is the same cut ARIMA makes
        # at the price level: the first holdout return is the first move into
        # a holdout price. Index from the front so holdout_days=0 keeps all.
        holdout_start = len(series_returns) - holdout_days
        modelling_returns = series_returns[:holdout_start]
        window_count = len(modelling_returns) - WINDOW_LENGTH
        val_count = max(1, window_count * VALIDATION_PERCENT // 100)
        train_count = window_count - val_count
        split_plans.append((series_returns[holdout_start:], modelling_returns, train_count, val_count))

    # Only returns that some training window touches, as input or target,
    # feed the scaler. Validation targets and the holdout stay unseen.
    training_returns = np.concatenate([
        modelling_returns[:WINDOW_LENGTH + train_count]
        for _, modelling_returns, train_count, _ in split_plans
    ])
    spread = float(np.std(training_returns))
    if spread == 0.0:
        raise ValueError("training returns have zero variance; cannot standardise")
    scaler = ReturnScaler(mean=float(np.mean(training_returns)), std=spread)

    train_input_parts, train_target_parts = [], []
    val_input_parts, val_target_parts = [], []
    holdout_seeds, holdout_returns = [], []

    for series_holdout, modelling_returns, train_count, val_count in split_plans:
        scaled_run = scaler.scale(modelling_returns)

        train_inputs, train_targets = _stack_windows(scaled_run, train_count, WINDOW_LENGTH)
        val_inputs, val_targets = _stack_windows(
            scaled_run, val_count, WINDOW_LENGTH + train_count
        )
        train_input_parts.append(train_inputs)
        train_target_parts.append(train_targets)
        val_input_parts.append(val_inputs)
        val_target_parts.append(val_targets)

        holdout_seeds.append(scaled_run[-WINDOW_LENGTH:].astype(np.float32)[:, None])
        holdout_returns.append(series_holdout)

    # float32 because that is what torch layers expect by default.
    return SequenceWindows(
        train_inputs=np.concatenate(train_input_parts).astype(np.float32)[..., None],
        train_targets=np.concatenate(train_target_parts).astype(np.float32),
        val_inputs=np.concatenate(val_input_parts).astype(np.float32)[..., None],
        val_targets=np.concatenate(val_target_parts).astype(np.float32),
        scaler=scaler,
        holdout_seeds=holdout_seeds,
        holdout_returns=holdout_returns,
    )
