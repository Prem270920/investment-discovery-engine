"""
ARIMA forecasting engine — validated returns-vs-price approach.

For each asset we fit TWO competing ARIMA models:
  * PRICE model:   ARIMA on raw closing prices 
  * RETURNS model: ARIMA on daily returns, then reconstruct the price path

"""


import warnings
import logging

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.getLogger("statsmodels").setLevel(logging.ERROR)

from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tools.sm_exceptions import ValueWarning
from statsmodels.tools.sm_exceptions import ConvergenceWarning

warnings.simplefilter("ignore", ValueWarning)
warnings.simplefilter("ignore", ConvergenceWarning)

HORIZON_DAYS = 30   # 6 trading weeks
BACKTEST_DAYS = 30  # held-out window for measuring error
CONFIDENCE = 0.05  

# AIC grid — kept modest so 56 assets x 2 models stays tractable
P_RANGE = range(0, 3)
D_RANGE = range(0, 2)
Q_RANGE = range(0, 3)

def _ensure_forecastable_index(series: pd.Series) -> pd.Series:
    """statsmodels needs a proper time index (or a plain RangeIndex) to forecast"""
    return pd.Series(series.values, index=pd.RangeIndex(len(series)))

def _best_arima(series: pd.Series):
    """Grid-search small (p,d,q) by AIC. Returns (fitted_model, order) or None"""
    series = pd.Series(np.asarray(series, dtype=float), index=pd.RangeIndex(len(series)))

    best = None
    best_aic = np.inf
    best_order = None
    last_error = None

    for p in P_RANGE:
        for d in D_RANGE:
            for q in Q_RANGE:
                if p == 0 and q == 0:
                    continue  # degenerate
                try:
                    model = ARIMA(series, order=(p, d, q)).fit()
                    if model.aic < best_aic:
                        best_aic, best, best_order = model.aic, model, (p, d, q)
                except Exception as exc:
                    last_error = exc
                    continue

    if best is None and last_error is not None:
        logging.getLogger("forecasting").warning(
            "no ARIMA order converged; last error: %s: %s",
            type(last_error).__name__, last_error,
        )

    return (best, best_order) if best is not None else (None, None)


def _rmse_pct(actual: np.ndarray, predicted: np.ndarray):

    rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    denom = float(np.mean(actual)) or 1.0
    return (rmse / denom) * 100.0

def _backtest_price_model(prices: pd.Series):
    """Fit price-ARIMA on all but the last BACKTEST_DAYS, forecast that window,
    return % error vs actual. None if it can't fit"""
    if len(prices) <= BACKTEST_DAYS + 20:
        return None
    train, test = prices[:-BACKTEST_DAYS], prices[-BACKTEST_DAYS:]
    model, _ = _best_arima(train)
    if model is None:
        return None
    fc = model.forecast(steps=BACKTEST_DAYS)
    return _rmse_pct(test.values, np.asarray(fc))


def _backtest_returns_model(prices: pd.Series):
    """Same, but model daily returns then reconstruct the price path."""
    if len(prices) <= BACKTEST_DAYS + 20:
        return None
    train, test = prices[:-BACKTEST_DAYS], prices[-BACKTEST_DAYS:]
    returns = train.pct_change().dropna()
    model, _ = _best_arima(returns)
    if model is None:
        return None
    fc_returns = np.asarray(model.forecast(steps=BACKTEST_DAYS))
    # Reconstruct prices: each day compounds the previous by (1 + return).
    last_price = float(train.iloc[-1])
    reconstructed = []
    p = last_price
    for r in fc_returns:
        p = p * (1 + r)
        reconstructed.append(p)
    return _rmse_pct(test.values, np.array(reconstructed))


def forecast_asset(prices: pd.Series):
    """Produce a forecast for one asset, choosing price- vs returns-ARIMA by
    backtest, and returning the winner's forward projection + measured error.
    Returns None if the asset has insufficient history or the ARIMA fit fails.
    """
    prices = prices.dropna()
    if len(prices) < BACKTEST_DAYS + 40:
        return None
    
    prices = _ensure_forecastable_index(prices)

    # Backtest both methods on held-out data.
    price_err = _backtest_price_model(prices)
    returns_err = _backtest_returns_model(prices)

    if price_err is None and returns_err is None:
        return None

    # Pick the winner (lower held-out error). Ties/one-None -> the available one.
    if returns_err is None:
        method = "price"
    elif price_err is None:
        method = "returns"
    else:
        method = "returns" if returns_err <= price_err else "price"
    backtest_error = returns_err if method == "returns" else price_err

    # Refit the winning method on ALL data and forecast forward
    if method == "price":
        model, order = _best_arima(prices)
        if model is None:
            return None
        fc = model.get_forecast(steps=HORIZON_DAYS)
        predicted = np.asarray(fc.predicted_mean)
        ci = fc.conf_int(alpha=CONFIDENCE)
        lower = np.asarray(ci)[:, 0]
        upper = np.asarray(ci)[:, 1]
    else:
        returns = prices.pct_change().dropna()
        model, order = _best_arima(returns)
        if model is None:
            return None
        fc = model.get_forecast(steps=HORIZON_DAYS)
        r_mean = np.asarray(fc.predicted_mean)
        r_ci = np.asarray(fc.conf_int(alpha=CONFIDENCE))
        # Reconstruct price path + bands from forecasted returns.
        last = float(prices.iloc[-1])
        predicted, lower, upper = [], [], []
        p_mid = last

        # Per-step return uncertainty (half-width of the CI, in return units).
        # ARIMA's per-day CI is roughly constant, so we must ACCUMULATE it:
        # uncertainty about a 30-day-ahead price is far larger than about
        # tomorrow's. Variance of a sum of returns grows with the number of
        # steps, so the standard deviation grows with sqrt(n). Without this the
        # band stays a fixed % of price and understates risk.
        step_halfwidth = (r_ci[:, 1] - r_ci[:, 0]) / 2.0

        cumulative_var = 0.0
        for i in range(HORIZON_DAYS):
            p_mid = p_mid * (1 + r_mean[i])
            predicted.append(p_mid)

            cumulative_var += float(step_halfwidth[i]) ** 2
            cumulative_halfwidth = cumulative_var ** 0.5

            lower.append(p_mid * (1 - cumulative_halfwidth))
            upper.append(p_mid * (1 + cumulative_halfwidth))
        predicted = np.array(predicted)
        lower = np.array(lower)
        upper = np.array(upper)

    return {
        "method": method,
        "order": str(order),
        "backtest_error_pct": round(float(backtest_error), 2) if backtest_error else None,
        "horizon": HORIZON_DAYS,
        "predicted": [float(x) for x in predicted],
        "lower": [float(x) for x in lower],
        "upper": [float(x) for x in upper],
    }

def _self_test():
    """Fit on a synthetic trending-with-noise series to confirm it runs and the
    band widens with horizon."""
    print("Forecasting self-test\n" + "-" * 40)
    rng = np.random.default_rng(42)
    n = 250
    # trend + noise, always positive
    trend = np.linspace(100, 130, n)
    noise = rng.normal(0, 2, n).cumsum() * 0.3
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    prices = pd.Series(np.maximum(trend + noise, 1.0), index=idx)

    result = forecast_asset(prices)
    if result is None:
        print("could not fit (unexpected for this series)")
        return

    print(f"winning method: {result['method']}  order={result['order']}")
    print(f"backtest error: {result['backtest_error_pct']}%")
    print(f"horizon: {result['horizon']} days")
    print(f"day 1  band width: {result['upper'][0] - result['lower'][0]:.2f}")
    print(f"day {result['horizon']} band width: "
          f"{result['upper'][-1] - result['lower'][-1]:.2f}")


if __name__ == "__main__":
    _self_test()