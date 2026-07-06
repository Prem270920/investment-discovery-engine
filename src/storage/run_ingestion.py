"""
The persistence runner — fetch, normalize, and STORE.

This is the real pipeline entry point retains full price history 
so it can populate the prices table.

Flow:
    for each ticker:
        fetch .info + price history   (retry once on failure)
        normalize .info               (reject/skip on bad data)
        upsert asset + insert new price bars   (via repository)
    commit ONCE at the end (atomic run)

Transaction design: we commit a single time after all assets succeed. If the
run blows up partway, the whole thing rolls back — no half-written state.

"""

import logging
import time

import yfinance as yf

from src.processing.normalize import AssetValidationError, normalize_asset
from src.storage.database import Base, SessionLocal, engine
from src.storage.models import Asset
from src.storage.repository import insert_new_prices, upsert_asset

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_ingestion")

SAMPLE_TICKERS = ["VAS.AX", "CBA.AX", "VOO", "AAPL", "IVV.AX", "IVV"]
INFO_FIELDS = [
    "symbol", "shortName", "quoteType", "currency", "sector",
    "beta", "dividendYield", "marketCap", "trailingPE",
]
RETRY_BACKOFF_SECONDS = 2.0


HISTORY_PERIOD = "1y"

class FetchError(Exception):
    """Raised when usable raw data can't be retrieved for a ticker."""

def _fetch_raw_with_history(symbol: str):
    """Fetch (.info dict + latest_close) and the full price-history DataFrame."""
    ticker = yf.Ticker(symbol)

    info = ticker.info
    if not info or info.get("symbol") is None:
        raise FetchError(f"{symbol}: empty or symbol-less .info response")

    history = ticker.history(period=HISTORY_PERIOD)
    if history.empty:
        raise FetchError(f"{symbol}: empty price history")

    raw = {key: info.get(key) for key in INFO_FIELDS}
    raw["latest_close"] = float(history["Close"].iloc[-1])
    return raw, history

def _fetch_with_retry(symbol: str):
    """Fetch with exactly one retry on failure."""
    try:
        return _fetch_raw_with_history(symbol)
    except Exception as first_error:  # noqa: BLE001
        logger.warning(
            "fetch failed for %s (%s); retrying once in %.0fs",
            symbol, type(first_error).__name__, RETRY_BACKOFF_SECONDS,
        )
        time.sleep(RETRY_BACKOFF_SECONDS)
        try:
            return _fetch_raw_with_history(symbol)
        except Exception as second_error:  # noqa: BLE001
            raise FetchError(
                f"{symbol}: failed twice "
                f"({type(second_error).__name__}: {second_error})"
            ) from second_error
        
