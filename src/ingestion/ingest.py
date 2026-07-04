"""
End-to-end ingestion — fetch live, normalize, summarize.

This is the first real vertical slice of the pipeline's input end:
    yfinance fetch  ->  assemble raw dict  ->  normalize  ->  clean records

Failure strategy: SKIP-AND-LOG + RETRY-ONCE.
  * A transient fetch failure is retried exactly once after a short backoff.
  * Anything that fails twice, or is rejected by the normalizer, is skipped
    and recorded — never silently dropped.
  * The run ends with a summary distinguishing FETCH failures (yfinance's fault)
    from VALIDATION rejections (normalizer refusing bad data).
"""

import logging
import time

import yfinance as yf

from src.processing.normalize import (
    AssetValidationError,
    NormalizedAsset,
    normalize_asset,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

SAMPLE_TICKERS = ["VAS.AX", "CBA.AX", "VOO", "AAPL", "IVV.AX", "IVV"]

INFO_FIELDS = [
    "symbol", "shortName", "quoteType", "currency", "sector",
    "beta", "dividendYield", "marketCap", "trailingPE",
]

RETRY_BACKOFF_SECONDS = 2.0

class FetchError(Exception):
    """Raised when yfinance fails to fetch a ticker after retrying once."""


def _fetch_raw(symbol: str) -> dict:
    """Fetch one ticker's fundamentals + latest close into a single raw dict.

    Raises FetchError if the network call fails or no price data is available.
    """
    ticker = yf.Ticker(symbol)

    # .info can raise or return an empty-ish dict when Yahoo blips.
    info = ticker.info
    if not info or info.get("symbol") is None:
        raise FetchError(f"{symbol}: empty or symbol-less .info response")
    

    hist = ticker.history(period="5d")
    if hist.empty:
        raise FetchError(f"{symbol}: empty .history response")
    
    raw = {key: info.get(key) for key in INFO_FIELDS}
    raw["latest_close"] = float(hist["Close"].iloc[-1])
    return raw


def _fetch_with_retry(symbol: str) -> dict:
    """Fetch, retrying exactly once on failure after a short backoff.

    One retry catches the common transient yfinance blip; a second failure
    means the ticker is probably genuinely broken, so we stop and let the
    caller record it.
    """

    try:
        return _fetch_raw(symbol)
    except Exception as first_error:
        logger.warning(
            "fetch failed for %s (%s); retrying once in %.0fs",
            symbol, type(first_error).__name__, RETRY_BACKOFF_SECONDS,
        )
        time.sleep(RETRY_BACKOFF_SECONDS)
        try:
            return _fetch_raw(symbol)
        except Exception as second_error:
            raise FetchError(
                f"{symbol}: failed twice "
                f"({type(second_error).__name__}: {second_error})"
            ) from second_error
        

        