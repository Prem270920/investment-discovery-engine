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
logger = logging.getLogger("ingestion")

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
        

def ingest(tickers: list[str]) -> tuple[list[NormalizedAsset], dict[str, list[str]]]:
    """Ingest a list of tickers into clean NormalizedAsset records.

    Returns:
        (assets, failures) where failures maps a category to a list of
            'fetch'      -> couldn't get usable data from yfinance (after retry)
            'validation' -> data came back but our normalizer rejected it
    """      

    assets: list[NormalizedAsset] = []
    failures: dict[str, list[str]] = {"fetch": [], "validation": []}

    for symbol in tickers:
        logger.info("ingesting %s ...", symbol)

        # Stage 1: fetch (with one retry)
        try:
            raw = _fetch_with_retry(symbol)
        except FetchError as exc:
            logger.error("FETCH FAILED: %s", exc)
            failures["fetch"].append(str(exc))
            continue

        # Stage 2: normalize/validate
        try:
            asset = normalize_asset(raw)
        except AssetValidationError as exc:
            logger.error("REJECTED: %s", exc)
            failures["validation"].append(str(exc))
            continue

        assets.append(asset)

        for warning in asset.data_warnings:
            logger.warning("  data warning [%s]: %s", asset.symbol, warning)

    return assets, failures

def _print_summary(
    tickers: list[str],
    assets: list[NormalizedAsset],
    failures: dict[str, list[str]]) -> None:
    
    total = len(tickers)
    ok = len(assets)
    fetch_failed = len(failures["fetch"])
    rejected = len(failures["validation"])

    print("\n" + "=" * 60)
    print("INGESTION RUN SUMMARY")
    print("=" * 60)
    print(f"  requested : {total}")
    print(f"  succeeded : {ok}")
    print(f"  fetch fail: {fetch_failed}")
    print(f"  rejected  : {rejected}")

    if failures["fetch"]:
        print("\n  Fetch failures:")
        for reason in failures["fetch"]:
            print(f"    - {reason}")
    if failures["validation"]:
        print("\n  Validation rejections:")
        for reason in failures["validation"]:
            print(f"    - {reason}")

    print("\n  Clean assets:")
    for a in assets:
        warn_flag = f"  ⚠ {len(a.data_warnings)} warning(s)" if a.data_warnings else ""
        print(f"    {a.symbol:<8} {a.quote_type:<7} "
              f"underlying={a.underlying_market:<6} "
              f"close={a.latest_close:<10.2f}{warn_flag}")
    print("=" * 60)

def main() -> None:
    logger.info("starting ingestion run for %d tickers", len(SAMPLE_TICKERS))
    assets, failures = ingest(SAMPLE_TICKERS)
    _print_summary(SAMPLE_TICKERS, assets, failures)
    logger.info("ingestion run complete: %d clean assets", len(assets))


if __name__ == "__main__":
    main()

