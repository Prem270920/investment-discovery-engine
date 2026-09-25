"""
Error measures shared by every forecasting lens.

ARIMA and GRU are only comparable head to head if they are scored by exactly
the same formula, so the formula lives here rather than inside either model.
"""

import numpy as np


def rmse_pct_of_price(actual_prices, predicted_prices) -> float:
    """Root mean squared error expressed as a percentage of the mean actual price.

    Scaling by price lets a $5 stock and a $500 stock be judged on one scale.
    """
    actual = np.asarray(actual_prices, dtype=float)
    predicted = np.asarray(predicted_prices, dtype=float)
    if actual.shape != predicted.shape:
        raise ValueError(
            f"actual and predicted must line up, got {actual.shape} and {predicted.shape}"
        )
    if actual.size == 0:
        raise ValueError("cannot score an empty backtest window")

    rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    # A zero mean price would divide by zero; falling back to 1.0 reports the
    # raw RMSE instead. Kept exactly as the original ARIMA code had it so stored
    # results don't shift.
    mean_price = float(np.mean(actual)) or 1.0
    return (rmse / mean_price) * 100.0
