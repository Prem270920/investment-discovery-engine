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
        
def run() -> None:
    # Create tables if they don't exist yet
    # This is safe to call multiple times, and is idempotent.
    # it only creates what's missing, never drops or overwrites.
    Base.metadata.create_all(engine)
    logger.info("tables ensured (assets, prices)")

    failures = {"fetch": [], "validation": []}
    assets_stored = 0
    prices_inserted = 0

    session = SessionLocal()
    try:
        for symbol in SAMPLE_TICKERS:
            logger.info("processing %s ...", symbol)

            # --- fetch ---
            try:
                raw, history = _fetch_with_retry(symbol)
            except FetchError as exc:
                logger.error("FETCH FAILED: %s", exc)
                failures["fetch"].append(str(exc))
                continue

            # --- normalize ---
            try:
                asset = normalize_asset(raw)
            except AssetValidationError as exc:
                logger.error("REJECTED: %s", exc)
                failures["validation"].append(str(exc))
                continue

            for w in asset.data_warnings:
                logger.warning("  data warning [%s]: %s", asset.symbol, w)

            # store (asset must exist before its prices, for the FK)
            upsert_asset(session, asset)
            session.flush()  # ensure the asset row is visible for the FK
            prices_inserted += insert_new_prices(session, asset.symbol, history)
            assets_stored += 1

        # One commit for the whole run — atomic.
        session.commit()
        logger.info("committed: %d assets, %d new price bars",
                    assets_stored, prices_inserted)
        
    except Exception:
        session.rollback()
        logger.exception("run failed — rolled back, no partial data written")
        raise
    finally:
        session.close()


    # summary 
    print("\n" + "=" * 60)
    print("PERSISTENCE RUN SUMMARY")
    print("=" * 60)
    print(f"  assets stored/updated : {assets_stored}")
    print(f"  new price bars inserted: {prices_inserted}")
    print(f"  fetch failures         : {len(failures['fetch'])}")
    print(f"  validation rejections  : {len(failures['validation'])}")
    for reason in failures["fetch"]:
        print(f"    fetch: {reason}")
    for reason in failures["validation"]:
        print(f"    reject: {reason}")
    print("=" * 60)


if __name__ == "__main__":
    run()