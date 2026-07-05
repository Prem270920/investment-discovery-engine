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
"""


import logging

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.processing.normalize import NormalizedAsset
from src.storage.models import Asset, Price

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