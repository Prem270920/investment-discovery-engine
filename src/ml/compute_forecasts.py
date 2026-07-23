"""
Compute and store ARIMA forecasts for every asset.

Reads price history from the database, runs the validated
returns-vs-price ARIMA engine, and stores the winning forecast plus its measured
backtest error.


COST WARNING: each asset runs 3 AIC grid searches (price backtest, returns
backtest, final refit), so this stage takes minutes for the full universe.
The pipeline exposes --skip-forecasts for fast development runs.
"""

import logging
from datetime import timedelta

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.ml.forecasting import forecast_asset
from src.storage.models import Asset, Forecast, ForecastMeta, Price

logger = logging.getLogger("compute_forecasts")

def _load_close_series(session: Session, symbol: str):
    """Load a symbol's closing prices as a date-indexed Series."""
    rows = session.execute(
        select(Price.date, Price.close)
        .where(Price.symbol == symbol)
        .order_by(Price.date)
    ).all()
    if not rows:
        return pd.Series(dtype="float64")
    return pd.Series([r[1] for r in rows], index=pd.to_datetime([r[0] for r in rows]))


def _future_trading_dates(last_date, n: int) -> list:
    """Generate the next n weekday dates after last_date.

    Approximation: we skip weekends but not public holidays, since holiday
    calendars differ per exchange. Forecast dates are indicative anyway — the
    projection is educational, so exact calendar alignment isn't meaningful.
    """
    dates = []
    current = last_date
    while len(dates) < n:
        current = current + timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            dates.append(current)
    return dates


def compute_and_store_forecasts(session: Session) -> tuple[int, int]:
    """Forecast every non-benchmark asset. Returns (succeeded, skipped)."""

    assets = session.scalars(select(Asset).where(Asset.is_benchmark == False)).all()

    succeeded = 0
    skipped = 0

    for asset in assets:
        closes = _load_close_series(session, asset.symbol)
        if closes.empty:
            logger.warning("%s: no price history; skipping forecast", asset.symbol)
            skipped += 1
            continue

        try:
            result = forecast_asset(closes)
        except Exception as exc:
            logger.warning("%s: forecast failed (%s); skipping",
                           asset.symbol, type(exc).__name__)
            skipped += 1
            continue

        if result is None:
            logger.warning("%s: no ARIMA model converged; skipping", asset.symbol)
            skipped += 1
            continue

        # Replace any previous forecast for this asset
        # projection each run, not accumulated history.
        session.execute(delete(Forecast).where(Forecast.symbol == asset.symbol))

        last_date = closes.index[-1].date()
        future_dates = _future_trading_dates(last_date, result["horizon"])

        for i, date in enumerate(future_dates):
            session.add(Forecast(
                symbol=asset.symbol,
                date=date,
                predicted=result["predicted"][i],
                lower=result["lower"][i],
                upper=result["upper"][i],
            ))

        meta = session.get(ForecastMeta, asset.symbol)
        if meta is None:
            session.add(ForecastMeta(
                symbol=asset.symbol,
                method=result["method"],
                arima_order=result["order"],
                backtest_error_pct=result["backtest_error_pct"],
                horizon_days=result["horizon"],
            ))
        else:
            meta.method = result["method"]
            meta.arima_order = result["order"]
            meta.backtest_error_pct = result["backtest_error_pct"]
            meta.horizon_days = result["horizon"]


        logger.info(
            "%s: %s model %s, backtest error %.2f%%",
            asset.symbol, result["method"], result["order"],
            result["backtest_error_pct"] if result["backtest_error_pct"] else float("nan"),
        )
        succeeded += 1

    return succeeded, skipped
