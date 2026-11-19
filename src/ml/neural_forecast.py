"""
GRU forecasting lens, run head to head against the ARIMA returns model.


The protocol copies ARIMA's step for step so the two error numbers mean the
same thing: same holdout, same recursive 30 day backtest, same price rebuild
from returns, same scoring function, same way of widening the band.
"""

import copy
import logging
import random
from functools import lru_cache

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.ml.forecast_metrics import rmse_pct_of_price
from src.ml.forecasting import BACKTEST_DAYS, CONFIDENCE, HORIZON_DAYS
from src.ml.optional_deps import torch_available
from src.ml.sequence_windows import build_sequence_windows, min_prices_for

logger = logging.getLogger("neural_forecast")

SEED = 42

HIDDEN_SIZE = 32
DROPOUT = 0.1
LEARNING_RATE = 1e-3
BATCH_SIZE = 32
MAX_EPOCHS = 200
PATIENCE = 15

# Two sided z for the same confidence level ARIMA's conf_int uses (1.96 at 95%).
BAND_Z = float(norm.ppf(1 - CONFIDENCE / 2))


class TorchUnavailableError(RuntimeError):
    """torch is missing, broken, or switched off with DISCOVERY_DISABLE_TORCH=1."""


def _require_torch():
    if not torch_available():
        raise TorchUnavailableError("torch unavailable; GRU forecasts are skipped")
    import torch
    return torch


@lru_cache(maxsize=1)
def _gru_regressor_class():
    # Built on first use because subclassing nn.Module needs torch imported.
    torch = _require_torch()

    class GruRegressor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.gru = torch.nn.GRU(
                input_size=1, hidden_size=HIDDEN_SIZE, num_layers=1, batch_first=True
            )
            # nn.GRU's own dropout argument only acts between stacked layers,
            # so with one layer it would do nothing. Applied to the head instead.
            self.dropout = torch.nn.Dropout(DROPOUT)
            self.head = torch.nn.Linear(HIDDEN_SIZE, 1)

        def forward(self, return_windows):
            _, final_hidden = self.gru(return_windows)
            return self.head(self.dropout(final_hidden[-1])).squeeze(-1)

    return GruRegressor


def _seed_everything(torch):
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.use_deterministic_algorithms(True)


def _train(torch, windows):
    """Fit a fresh seeded GRU with early stopping. Returns (model, best_epoch)."""
    _seed_everything(torch)
    model = _gru_regressor_class()()
    optimiser = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    squared_error = torch.nn.MSELoss()

    train_inputs = torch.from_numpy(windows.train_inputs)
    train_targets = torch.from_numpy(windows.train_targets)
    val_inputs = torch.from_numpy(windows.val_inputs)
    val_targets = torch.from_numpy(windows.val_targets)

    # A dedicated generator keeps batch order tied to SEED even if something
    # else draws from torch's global generator in between.
    batch_shuffler = torch.Generator().manual_seed(SEED)

    best_val_loss = float("inf")
    best_weights = None
    best_epoch = 0
    epochs_without_gain = 0

    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        shuffled_rows = torch.randperm(len(train_inputs), generator=batch_shuffler)
        for batch_start in range(0, len(shuffled_rows), BATCH_SIZE):
            batch_rows = shuffled_rows[batch_start:batch_start + BATCH_SIZE]
            optimiser.zero_grad()
            batch_loss = squared_error(model(train_inputs[batch_rows]), train_targets[batch_rows])
            batch_loss.backward()
            optimiser.step()

        model.eval()
        with torch.no_grad():
            val_loss = squared_error(model(val_inputs), val_targets).item()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_weights = copy.deepcopy(model.state_dict())
            best_epoch = epoch
            epochs_without_gain = 0
        else:
            epochs_without_gain += 1
            if epochs_without_gain >= PATIENCE:
                break

    model.load_state_dict(best_weights)
    model.eval()
    return model, best_epoch


def _roll_forward(torch, model, seed_window, steps):
    """Recursive multi step forecast in scaled return space: each prediction
    becomes the newest input for the next one, as ARIMA's forecast does."""
    rolling_window = torch.from_numpy(seed_window).unsqueeze(0)  # (1, WINDOW_LENGTH, 1)
    scaled_path = []
    with torch.no_grad():
        for _ in range(steps):
            next_scaled = model(rolling_window)
            scaled_path.append(float(next_scaled.item()))
            rolling_window = torch.cat([rolling_window[:, 1:, :], next_scaled.view(1, 1, 1)], dim=1)
    return np.array(scaled_path)


def _validation_residual_std(torch, model, windows) -> float:
    """Spread of one step ahead validation errors, in raw return units."""
    with torch.no_grad():
        val_predictions = model(torch.from_numpy(windows.val_inputs)).numpy()
    # Unscaling a difference only needs the std; the mean cancels out.
    residuals = (windows.val_targets.astype(float) - val_predictions.astype(float)) * windows.scaler.std
    return float(np.std(residuals))


def _compound_returns(last_price: float, daily_returns) -> np.ndarray:
    """Same price rebuild as the ARIMA returns model: compound day by day."""
    price_path = []
    running_price = last_price
    for daily_return in daily_returns:
        running_price = running_price * (1 + daily_return)
        price_path.append(running_price)
    return np.array(price_path)


def _accumulated_band(predicted_prices, step_halfwidths):
    """Same widening as the ARIMA returns path: add per step variances so the
    half width grows with the square root of the horizon."""
    lower, upper = [], []
    cumulative_var = 0.0
    for predicted_price, step_halfwidth in zip(predicted_prices, step_halfwidths):
        cumulative_var += float(step_halfwidth) ** 2
        cumulative_halfwidth = cumulative_var ** 0.5
        lower.append(predicted_price * (1 - cumulative_halfwidth))
        upper.append(predicted_price * (1 + cumulative_halfwidth))
    return np.array(lower), np.array(upper)


def _clean_closes(prices) -> np.ndarray:
    # forecast_asset drops missing closes before anything else; so do we.
    return pd.Series(prices).dropna().to_numpy(dtype=float)


def _backtest(torch, closes: np.ndarray):
    """Train without the last BACKTEST_DAYS bars, forecast them, score like ARIMA."""
    windows = build_sequence_windows([closes])
    model, best_epoch = _train(torch, windows)
    scaled_path = _roll_forward(torch, model, windows.holdout_seeds[0], BACKTEST_DAYS)
    rebuilt_prices = _compound_returns(
        float(closes[-BACKTEST_DAYS - 1]), windows.scaler.unscale(scaled_path)
    )
    return rmse_pct_of_price(closes[-BACKTEST_DAYS:], rebuilt_prices), best_epoch


def backtest_rmse_pct(prices) -> float | None:
    """Unrounded GRU backtest error for one asset, or None if history is too short."""
    torch = _require_torch()
    closes = _clean_closes(prices)
    if len(closes) < min_prices_for(BACKTEST_DAYS):
        return None
    backtest_error, _ = _backtest(torch, closes)
    return backtest_error


def forecast_asset_gru(prices):
    """GRU counterpart of forecasting.forecast_asset for one asset.

    Returns None if history is too short. Raises TorchUnavailableError when
    torch can't be used.
    """
    torch = _require_torch()
    closes = _clean_closes(prices)
    if len(closes) < min_prices_for(BACKTEST_DAYS):
        return None

    backtest_error, backtest_epoch = _backtest(torch, closes)

    # Forward model: same seed, every bar available, validation slice still
    # held back for early stopping and for sizing the band.
    forward_windows = build_sequence_windows([closes], holdout_days=0)
    forward_model, forward_epoch = _train(torch, forward_windows)
    scaled_path = _roll_forward(torch, forward_model, forward_windows.holdout_seeds[0], HORIZON_DAYS)
    predicted = _compound_returns(float(closes[-1]), forward_windows.scaler.unscale(scaled_path))

    residual_std = _validation_residual_std(torch, forward_model, forward_windows)
    step_halfwidths = np.full(HORIZON_DAYS, BAND_Z * residual_std)
    lower, upper = _accumulated_band(predicted, step_halfwidths)

    logger.info(
        "GRU backtest %.2f%% (best epoch %d), forward model best epoch %d",
        backtest_error, backtest_epoch, forward_epoch,
    )
    return {
        "method": "gru",
        "backtest_error_pct": round(float(backtest_error), 2),
        "horizon": HORIZON_DAYS,
        "predicted": [float(x) for x in predicted],
        "lower": [float(x) for x in lower],
        "upper": [float(x) for x in upper],
        "backtest_best_epoch": backtest_epoch,
        "forward_best_epoch": forward_epoch,
    }
