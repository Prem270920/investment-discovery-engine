"""
Full pipeline orchestrator

The entry point that runs the complete flow in one atomic transaction:

      -> ingest assets      (fetch, normalize, store)
      -> ingest benchmarks  (^AXJO, ^GSPC as is_benchmark rows)
      -> compute metrics    (volatility, Sharpe, beta from stored prices)
      -> commit once

if any stage fails, the whole run rolls back — we never leave the DB half-populated 
(e.g. assets but no metrics, or prices missing their benchmarks).
"""

import argparse
import logging
import time

import yfinance as yf

from src.ingestion.benchmarks import ingest_benchmarks
from src.ml.compute_metrics import compute_and_store_metrics
from src.processing.normalize import AssetValidationError, normalize_asset
from src.storage.database import Base, SessionLocal, engine
from src.storage.repository import insert_new_prices, upsert_asset
from src.ingestion.universe import load_universe
from src.ml.clustering import cluster_and_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")

SAMPLE_TICKERS = ["VAS.AX", "CBA.AX", "VOO", "AAPL", "IVV.AX", "IVV"]
INFO_FIELDS = [
    "symbol", "shortName", "quoteType", "currency", "sector",
    "beta", "dividendYield", "marketCap", "trailingPE",
]
HISTORY_PERIOD = "1y"
RETRY_BACKOFF_SECONDS = 2.0

class FetchError(Exception):
    """Raised when usable raw data can't be retrieved for a ticker."""


def _fetch_raw_with_history(symbol: str):
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
        

def _ingest_assets(session) -> tuple[int, int, dict]:
    """Fetch, normalize, and store the investable assets. Returns
    (assets_stored, price_bars_inserted, failures)."""
    failures = {"fetch": [], "validation": []}
    assets_stored = 0
    prices_inserted = 0

    for symbol in load_universe():
        logger.info("processing asset %s ...", symbol)
        try:
            raw, history = _fetch_with_retry(symbol)
        except FetchError as exc:
            logger.error("FETCH FAILED: %s", exc)
            failures["fetch"].append(str(exc))
            continue

        try:
            asset = normalize_asset(raw)
        except AssetValidationError as exc:
            logger.error("REJECTED: %s", exc)
            failures["validation"].append(str(exc))
            continue

        for w in asset.data_warnings:
            logger.warning("  data warning [%s]: %s", asset.symbol, w)

        upsert_asset(session, asset)
        session.flush()
        prices_inserted += insert_new_prices(session, asset.symbol, history)
        assets_stored += 1

    return assets_stored, prices_inserted, failures

assets_clustered = 0

def run(recreate: bool = False) -> None:
    if recreate:
        logger.warning("--recreate: dropping ALL tables first")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    logger.info("schema ready (assets, prices, asset_metrics)")

    session = SessionLocal()
    try:
        # Stage 1: investable assets
        assets_stored, prices_inserted, failures = _ingest_assets(session)

        # Stage 2: benchmarks (reference series for beta)
        benchmark_bars = ingest_benchmarks(session)
        session.flush()  # ensure benchmark prices are queryable for stage 3

        # Stage 3: compute metrics from everything now staged
        metrics_computed = compute_and_store_metrics(session)

        # Stage 4: cluster assets on their computed metrics.
        session.flush()
        try:
            assets_clustered = cluster_and_store(session)
        except Exception as exc:
            logger.warning("clustering skipped: %s", exc)
            assets_clustered = 0

        session.commit()
        logger.info("committed full pipeline run")

    except Exception:
        session.rollback()
        logger.exception("pipeline failed — rolled back, no partial data")
        raise
    finally:
        session.close()

    print("\n" + "=" * 60)
    print("FULL PIPELINE RUN SUMMARY")
    print("=" * 60)
    print(f"  assets stored/updated  : {assets_stored}")
    print(f"  asset price bars added : {prices_inserted}")
    print(f"  benchmark bars added   : {benchmark_bars}")
    print(f"  metrics computed       : {metrics_computed}")
    print(f"  assets clustered       : {assets_clustered}")
    print(f"  fetch failures         : {len(failures['fetch'])}")
    print(f"  validation rejections  : {len(failures['validation'])}")
    for reason in failures["fetch"]:
        print(f"    fetch: {reason}")
    for reason in failures["validation"]:
        print(f"    reject: {reason}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full ingestion + metrics pipeline")
    parser.add_argument(
        "--recreate", action="store_true",
        help="DROP all tables before running (clean rebuild)",
    )
    args = parser.parse_args()
    run(recreate=args.recreate)


if __name__ == "__main__":
    main()



