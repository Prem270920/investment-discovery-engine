"""
Repository — the single gateway for persisting data

Persistence rules:
  * assets  -> UPSERT BY SYMBOL: update the existing row if present, else insert.
               An asset's facts (price, yield) change over time; we keep one
               current row per ticker.
  * prices  -> INSERT NEW DATES ONLY: each (symbol, date) bar is an immutable
               historical fact. We add dates we don't have and never touch
               existing ones. The UNIQUE(symbol, date) constraint is the
               backstop that makes duplicates impossible.
  * forecasts -> REPLACE PER LENS: each run swaps out one model's projection
               for an asset and leaves the other model's rows alone.
"""


import logging

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.processing.normalize import NormalizedAsset
from src.storage.models import ARIMA_LENS, Asset, Forecast, ForecastMeta, Price

logger = logging.getLogger("storage")

def upsert_asset(session: Session, asset: NormalizedAsset) -> None:
    """Update the asset row if it exists, otherwise insert it"""
    existing = session.get(Asset, asset.symbol)

    if existing is None:
        # Insert path.
        row = Asset(
            symbol=asset.symbol,
            short_name=asset.short_name,
            quote_type=asset.quote_type,
            currency=asset.currency,
            listed_exchange=asset.listed_exchange,
            underlying_market=asset.underlying_market,
            sector=asset.sector,
            category=asset.category,
            beta=asset.beta,
            dividend_yield=asset.dividend_yield,
            market_cap=asset.market_cap,
            trailing_pe=asset.trailing_pe,
            latest_close=asset.latest_close,
        )
        session.add(row)
        logger.info("inserted new asset %s", asset.symbol)
    else:
        # Update path — refresh the mutable facts.
        existing.short_name = asset.short_name
        existing.quote_type = asset.quote_type
        existing.currency = asset.currency
        existing.listed_exchange = asset.listed_exchange
        existing.underlying_market = asset.underlying_market
        existing.sector = asset.sector
        existing.category = asset.category
        existing.beta = asset.beta
        existing.dividend_yield = asset.dividend_yield
        existing.market_cap = asset.market_cap
        existing.trailing_pe = asset.trailing_pe
        existing.latest_close = asset.latest_close
        logger.info("updated existing asset %s", asset.symbol)


def insert_new_prices(session: Session, symbol: str, history: pd.DataFrame) -> int:
    """Insert only price bars we don't already have for this symbol.
       Returns the number of new bars inserted.
    """
    if history.empty:
        logger.warning("no price history to insert for %s", symbol)
        return 0

    # Query the DB for all dates we already have for this symbol, so we can skip them.
    existing_dates = set(
        session.scalars(
            select(Price.date).where(Price.symbol == symbol)
        ).all()
    )

    new_count = 0
    for ts, bar in history.iterrows():
        bar_date = ts.date()
        if bar_date in existing_dates:
            continue  # immutable fact already stored — skip.

        session.add(
            Price(
                symbol=symbol,
                date=bar_date,
                open=float(bar["Open"]),
                high=float(bar["High"]),
                low=float(bar["Low"]),
                close=float(bar["Close"]),
                volume=int(bar["Volume"]),
            )
        )
        new_count += 1

    logger.info("%s: inserted %d new price bar(s)", symbol, new_count)
    return new_count


def replace_forecast(
    session: Session,
    symbol: str,
    dates: list,
    predicted: list[float],
    lower: list[float],
    upper: list[float],
    lens: str = ARIMA_LENS,
) -> int:
    """Swap in a fresh projection for one lens. Returns the points written."""
    if not (len(dates) == len(predicted) == len(lower) == len(upper)):
        raise ValueError(f"{symbol}: forecast columns have mismatched lengths")

    # Scoped to the lens so rerunning ARIMA never wipes a stored GRU path.
    session.execute(
        delete(Forecast).where(Forecast.symbol == symbol, Forecast.lens == lens)
    )
    for point_date, point_mid, point_low, point_high in zip(dates, predicted, lower, upper):
        session.add(Forecast(
            symbol=symbol,
            lens=lens,
            date=point_date,
            predicted=float(point_mid),
            lower=float(point_low),
            upper=float(point_high),
        ))
    return len(dates)


def get_forecast_points(
    session: Session, symbol: str, lens: str = ARIMA_LENS
) -> list[Forecast]:
    """One lens's projection for an asset, oldest date first."""
    return list(session.scalars(
        select(Forecast)
        .where(Forecast.symbol == symbol, Forecast.lens == lens)
        .order_by(Forecast.date)
    ).all())


def upsert_arima_meta(
    session: Session,
    symbol: str,
    method: str,
    arima_order: str,
    backtest_error_pct: float | None,
    horizon_days: int,
) -> ForecastMeta:
    """Write the ARIMA summary for an asset without disturbing its GRU fields."""
    meta = session.get(ForecastMeta, symbol)
    if meta is None:
        meta = ForecastMeta(symbol=symbol)
        session.add(meta)
    meta.method = method
    meta.arima_order = arima_order
    meta.backtest_error_pct = backtest_error_pct
    meta.horizon_days = horizon_days
    return meta


def update_gru_meta(
    session: Session,
    symbol: str,
    gru_status: str,
    gru_rmse_pct: float | None = None,
    head_to_head_winner: str | None = None,
) -> bool:
    """Record the GRU outcome on an asset's existing forecast summary.

    Returns False when there is no ARIMA summary to attach to. The row's
    required ARIMA columns can't be invented here, and a head to head needs
    both sides anyway.
    """
    meta = session.get(ForecastMeta, symbol)
    if meta is None:
        logger.warning("%s: no ARIMA forecast summary; GRU result not stored", symbol)
        return False
    meta.gru_status = gru_status
    meta.gru_rmse_pct = gru_rmse_pct
    meta.head_to_head_winner = head_to_head_winner
    return True


def get_forecast_meta(session: Session, symbol: str) -> ForecastMeta | None:
    """The forecast summary for an asset, carrying both lenses' fields."""
    return session.get(ForecastMeta, symbol)
