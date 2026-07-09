"""
Benchmark ingestion.

Benchmarks (^AXJO = S&P/ASX 200, ^GSPC = S&P 500) are REFERENCE series used only to compute beta.

Design: we store them in the same assets + prices tables (so their price bars
satisfy the prices -> assets foreign key), but flagged is_benchmark=True so the
API can filter them out of every carousel.

Benchmark -> home market mapping:
    ^AXJO -> AU
    ^GSPC -> US
"""

import logging
import time

import yfinance as yf

from src.storage.models import Asset
from src.storage.repository import insert_new_prices


logger = logging.getLogger("benchmarks")

BENCHMARKS = {
    "^AXJO": {"name": "S&P/ASX 200", "market": "AU", "currency": "AUD"},
    "^GSPC": {"name": "S&P 500", "market": "US", "currency": "USD"},
}

HISTORY_PERIOD = "1y"
RETRY_BACKOFF_SECONDS = 2.0

class BenchmarkFetchError(Exception):
    """Raised when a benchmark's data can't be retrieved."""


def _fetch_benchmark_history(symbol: str):
    """Fetch a benchmark's price history + latest close."""
    ticker = yf.Ticker(symbol)
    history = ticker.history(period=HISTORY_PERIOD)
    if history.empty:
        raise BenchmarkFetchError(f"{symbol}: empty price history")
    latest_close = float(history["Close"].iloc[-1])
    return history, latest_close

def _fetch_with_retry(symbol: str):
    """One retry on failure — same resilience pattern as asset ingestion."""
    try:
        return _fetch_benchmark_history(symbol)
    except Exception as first_error:
        logger.warning(
            "benchmark fetch failed for %s (%s); retrying once in %.0fs",
            symbol, type(first_error).__name__, RETRY_BACKOFF_SECONDS,
        )
        time.sleep(RETRY_BACKOFF_SECONDS)
        try:
            return _fetch_benchmark_history(symbol)
        except Exception as second_error:
            raise BenchmarkFetchError(
                f"{symbol}: failed twice "
                f"({type(second_error).__name__}: {second_error})"
            ) from second_error
        

def upsert_benchmark(session, symbol: str, meta: dict, latest_close: float) -> None:
    """Insert or update a benchmark's Asset row (is_benchmark=True)."""

    existing = session.get(Asset, symbol)
    if existing is None:
        session.add(
            Asset(
                symbol=symbol,
                short_name=meta["name"],
                quote_type="INDEX",
                currency=meta["currency"],
                listed_exchange=meta["market"],   # AU / US
                underlying_market=meta["market"],  # same for an index
                latest_close=latest_close,
                is_benchmark=True,
            )
        )
        logger.info("inserted benchmark %s (%s)", symbol, meta["name"])
    else:
        existing.short_name = meta["name"]
        existing.latest_close = latest_close
        existing.is_benchmark = True
        logger.info("updated benchmark %s", symbol)


def ingest_benchmarks(session) -> int:
    """Fetch and persist all benchmarks. Returns count of new price bars.

    Takes a session (caller controls the transaction) — same pattern as the
    asset repository, so benchmark + asset ingestion can share one atomic run.
    """
    new_bars = 0
    for symbol, meta in BENCHMARKS.items():
        logger.info("processing benchmark %s ...", symbol)
        try:
            history, latest_close = _fetch_with_retry(symbol)
        except BenchmarkFetchError as exc:
            logger.error("BENCHMARK FETCH FAILED: %s", exc)
            continue

        upsert_benchmark(session, symbol, meta, latest_close)
        session.flush()  # asset row visible before its prices (FK)
        new_bars += insert_new_prices(session, symbol, history)

    return new_bars


