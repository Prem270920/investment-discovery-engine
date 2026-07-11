"""
Pure risk-metric functions 

Each function takes price/return data and returns a number. 

Metrics computed:
  * daily returns       — the basis for everything else
  * annualized volatility — how much the asset swings (risk proxy that works
                            for ETFs too, unlike Yahoo's null beta)
  * Sharpe ratio        — return per unit of risk
  * beta                — sensitivity to a benchmark (covariance / variance)
"""

import numpy as np
import pandas as pd

# 252 trading days in a year
TRADING_DAYS_PER_YEAR = 252

# 52 weeks in a year — annualization factor for weekly-interval metrics.
TRADING_WEEKS_PER_YEAR = 52

# Fixed per-market risk-free rates (annual)
RISK_FREE_RATES = {
    "AU": 0.0435,   # ~RBA cash rate proxy
    "US": 0.0430,   # ~US short-term treasury proxy
    "GLOBAL": 0.0430,  # fall back to US-like for globally-diversified assets
}
DEFAULT_RISK_FREE = 0.0430

def daily_returns(close_prices: pd.Series) -> pd.Series:
    """Simple daily returns from a series of closing prices.

    return_t = (price_t - price_{t-1}) / price_{t-1}

    The first value is NaN (no prior day) and is dropped.
    """
    if close_prices is None or len(close_prices) < 2:
        return pd.Series(dtype="float64")
    returns = close_prices.pct_change().dropna()
    return returns

def weekly_returns(close_prices: pd.Series) -> pd.Series:
    """Weekly (week-ending-Friday) returns from a series of closing prices.

    beta aligns TWO price series across markets. ASX and US trade on different calendars AND timezones.
    the ASX close for a given calendar day reflects information ~a day out of sync with the US close.
    Joining daily returns across markets therefore misaligns them and collapses beta toward zero 

    Resampling to weekly makes that sub-daily offset negligible: being one day
    off barely matters across a 5-day window.

    Note: this is used ONLY for beta. Volatility and Sharpe stay on daily data
    (they use a single asset's own returns, so no cross-market alignment issue).
    """
    if close_prices is None or len(close_prices) < 2:
        return pd.Series(dtype="float64")
    # 'W-FRI' = week ending Friday. last() takes each week's final close.
    weekly_close = close_prices.resample("W-FRI").last().dropna()
    if len(weekly_close) < 2:
        return pd.Series(dtype="float64")
    return weekly_close.pct_change().dropna()

def convert_to_usd(aud_close: pd.Series, audusd_close: pd.Series) -> pd.Series:
    """Convert an AUD-priced series to USD using the AUD/USD rate.

    *** CURRENTLY UNUSED — retained for documentation. ***
    We built this to currency-strip cross-listed ETFs (IVV.AX) so their beta
    would reflect pure underlying exposure. It only recovered beta from 0.33 to
    0.67, not the expected ~1.0, because yfinance's daily FX bar and the ASX
    equity close are snapped at different times of day, so the multiplication
    removes some FX effect while injecting timing noise. We chose instead to
    report the honest FX-inclusive beta. See compute_metrics.py and the README.
    """

def annualized_volatility(returns: pd.Series) -> float | None:
    """Annualized standard deviation of daily returns.

    daily_vol = std(daily_returns)
    annual_vol = daily_vol * sqrt(252)

    Returns None if there aren't enough data points for a meaningful figure.
    """
    if returns is None or len(returns) < 2:
        return None
    daily_vol = float(returns.std(ddof=1))  
    return daily_vol * np.sqrt(TRADING_DAYS_PER_YEAR)

def sharpe_ratio(returns: pd.Series, risk_free_annual: float) -> float | None:
    """Annualized Sharpe ratio: excess return per unit of volatility.

    We annualize the mean daily return and the volatility, then:
        sharpe = (annual_return - risk_free) / annual_volatility

    Returns None if volatility is zero (undefined ratio) or data is too thin.
    """
    if returns is None or len(returns) < 2:
        return None

    annual_return = float(returns.mean()) * TRADING_DAYS_PER_YEAR
    annual_vol = annualized_volatility(returns)

    if annual_vol is None or annual_vol == 0:
        return None

    return (annual_return - risk_free_annual) / annual_vol

def beta(asset_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    """Beta: sensitivity of the asset to its benchmark.

        beta = cov(asset, benchmark) / var(benchmark)

    Returns None if the benchmark has zero variance or data is too thin.
    """
    if asset_returns is None or benchmark_returns is None:
        return None


    aligned = pd.concat(
        [asset_returns.rename("asset"), benchmark_returns.rename("bench")],
        axis=1,
        join="inner",
    ).dropna()

    if len(aligned) < 2:
        return None

    covariance = float(aligned["asset"].cov(aligned["bench"]))
    benchmark_variance = float(aligned["bench"].var(ddof=1))

    if benchmark_variance == 0:
        return None

    return covariance / benchmark_variance

def risk_free_for_market(underlying_market: str) -> float:
    """Return the fixed annual risk-free rate for a given market."""
    return RISK_FREE_RATES.get(underlying_market, DEFAULT_RISK_FREE)



# Self-test: verify formulas against an example.

def _self_test() -> None:
    """Run the math on a small synthetic series we can verify it manually"""
    print("Risk-metric self-test\n" + "-" * 40)

    # A simple price series where we can sanity-check the returns.
    prices = pd.Series(
        [100.0, 101.0, 102.0, 100.0, 103.0],
        index=pd.to_datetime(
            ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"]
        ),
    )
    rets = daily_returns(prices)
    print("prices:", list(prices.values))
    print("daily returns (%):", [round(r * 100, 3) for r in rets.values])

    vol = annualized_volatility(rets)
    print(f"annualized volatility: {vol:.4f}")

    sharpe = sharpe_ratio(rets, risk_free_annual=0.043)
    print(f"sharpe (rf=4.3%): {sharpe:.4f}")

    # Beta of a series against ITSELF must equal exactly 1.0 — a perfect
    self_beta = beta(rets, rets)
    print(f"beta vs itself (must be 1.0): {self_beta:.6f}")

    # Beta against a flat (zero-variance) benchmark must be None (undefined).
    flat = pd.Series([0.0] * len(rets), index=rets.index)
    flat_beta = beta(rets, flat)
    print(f"beta vs flat benchmark (must be None): {flat_beta}")

    print("-" * 40)
    print("Self-test complete. Verify beta-vs-itself is 1.0 above.")


if __name__ == "__main__":
    _self_test()