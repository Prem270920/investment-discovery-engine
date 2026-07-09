"""
Compute and store risk metrics.

Reads price history FROM THE DATABASE, computes volatility/Sharpe/beta via the pure functions in
risk_metrics.py, and upserts one row per asset into asset_metrics.

Benchmark selection: an asset's beta is measured against the
benchmark for its UNDERLYING_MARKET, not its listing exchange. So IVV.AX
(listed ASX, underlying US) is measured against ^GSPC — capturing its real
risk character (it tracks the S&P 500), not its muted correlation with the ASX.
"""

import logging

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ml import risk_metrics
from src.storage.models import Asset, AssetMetric, Price

logger = logging.getLogger("compute_metrics")

# Which benchmark represents each underlying market.
MARKET_TO_BENCHMARK = {
    "AU": "^AXJO",
    "US": "^GSPC",
    "GLOBAL": "^GSPC",  
}

def _load_close_series(session: Session, symbol: str) -> pd.Series:
    """Load a symbol's closing prices from the DB as a date-indexed Series."""
    rows = session.execute(
        select(Price.date, Price.close)
        .where(Price.symbol == symbol)
        .order_by(Price.date)
    ).all()
    if not rows:
        return pd.Series(dtype="float64")
    dates = [r[0] for r in rows]
    closes = [r[1] for r in rows]
    return pd.Series(closes, index=pd.to_datetime(dates))

def compute_and_store_metrics(session: Session) -> int:
    """Compute metrics for every NON-benchmark asset and upsert them.

    Returns the number of assets whose metrics were computed.
    """

    # Pre-load benchmark return series once
    benchmark_returns: dict[str, pd.Series] = {}
    for market, bench_symbol in MARKET_TO_BENCHMARK.items():
        closes = _load_close_series(session, bench_symbol)
        if not closes.empty:
            benchmark_returns[bench_symbol] = risk_metrics.daily_returns(closes)
        else:
            logger.warning(
                "benchmark %s has no price data; beta unavailable for %s assets",
                bench_symbol, market,
            )

    # skip benchmarks themselves
    assets = session.scalars(select(Asset).where(Asset.is_benchmark == False)).all()

    computed = 0
    for asset in assets:
        closes = _load_close_series(session, asset.symbol)
        rets = risk_metrics.daily_returns(closes)

        if rets.empty:
            logger.warning("%s: no returns; skipping metrics", asset.symbol)
            continue

        vol = risk_metrics.annualized_volatility(rets)
        rf = risk_metrics.risk_free_for_market(asset.underlying_market)
        sharpe = risk_metrics.sharpe_ratio(rets, risk_free_annual=rf)

        # Beta vs the benchmark for this asset's UNDERLYING market.
        bench_symbol = MARKET_TO_BENCHMARK.get(asset.underlying_market)
        bench_rets = benchmark_returns.get(bench_symbol)
        asset_beta = (risk_metrics.beta(rets, bench_rets) if bench_rets is not None else None)

        # Upsert the metrics row
        existing = session.get(AssetMetric, asset.symbol)
        if existing is None:
            session.add(
                AssetMetric(
                    symbol=asset.symbol,
                    annualized_volatility=vol,
                    sharpe_ratio=sharpe,
                    beta=asset_beta,
                    benchmark_symbol=bench_symbol,
                )
            )
        else:
            existing.annualized_volatility = vol
            existing.sharpe_ratio = sharpe
            existing.beta = asset_beta
            existing.benchmark_symbol = bench_symbol

        logger.info(
            "%s: vol=%.4f sharpe=%s beta=%s vs %s",
            asset.symbol,
            vol if vol is not None else float("nan"),
            f"{sharpe:.4f}" if sharpe is not None else "None",
            f"{asset_beta:.4f}" if asset_beta is not None else "None",
            bench_symbol,
        )
        computed += 1

    return computed


