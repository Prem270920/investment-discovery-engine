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


