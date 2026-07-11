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
    # Pre-load benchmark WEEKLY returns once
    benchmark_returns: dict[str, pd.Series] = {}
    for market, bench_symbol in MARKET_TO_BENCHMARK.items():
        closes = _load_close_series(session, bench_symbol)
        if not closes.empty:
            # Benchmark returns are used ONLY for beta, so store them WEEKLY
            # (W-FRI) to fix cross-market date misalignment. See weekly_returns().
            benchmark_returns[bench_symbol] = risk_metrics.weekly_returns(closes)
        else:
            logger.warning(
                "benchmark %s has no price data; beta unavailable for %s assets",
                bench_symbol, market,
            )

    # Only compute for real, browsable assets — skip benchmarks
    assets = session.scalars(
        select(Asset).where(Asset.is_benchmark == False)  # noqa: E712
    ).all()

    computed = 0
    for asset in assets:
        closes = _load_close_series(session, asset.symbol)
        daily_rets = risk_metrics.daily_returns(closes)

        if daily_rets.empty:
            logger.warning("%s: no returns; skipping metrics", asset.symbol)
            continue

        # Volatility & Sharpe: DAILY returns 
        vol = risk_metrics.annualized_volatility(daily_rets)
        rf = risk_metrics.risk_free_for_market(asset.underlying_market)
        sharpe = risk_metrics.sharpe_ratio(daily_rets, risk_free_annual=rf)

        # Beta: WEEKLY returns, in the asset's OWN currency
        #
        # DELIBERATE DESIGN DECISION (see README):
        # For cross-currency assets (e.g. IVV.AX: AUD-priced, US underlying), we
        # report the beta an investor ACTUALLY EXPERIENCES in their own currency,
        # NOT a currency-stripped "pure underlying exposure" figure.
        #
        # Why: IVV.AX holds the S&P 500, so its currency-stripped beta "should"
        # be ~1.0. But an unhedged AUD investor does NOT get 1:1 S&P exposure —
        # AUD/USD movements partially offset the underlying's moves, diluting the
        # relationship to ~0.33. That dilution is REAL, not an artifact.
        #
        # attempted currency-stripping (converting AUD closes to USD via
        # AUDUSD=X) and could only recover beta to ~0.67, not ~1.0. Diagnosis:
        # yfinance's daily FX bar and the ASX equity close are snapped at
        # DIFFERENT times of day, so multiplying them removes some FX effect
        # while injecting fresh timing noise. The free data cannot support a
        # clean strip. Rather than tune until we got a number we'd pre-decided
        # was "right", we report the honest, FX-inclusive figure.
        #
        # WEEKLY (W-FRI) resampling is retained: it genuinely does fix the
        # cross-market TIMEZONE misalignment (verified via a lag test — lag 0 is
        # optimal, so the weekly buckets are correctly aligned).
        bench_symbol = MARKET_TO_BENCHMARK.get(asset.underlying_market)
        bench_rets = benchmark_returns.get(bench_symbol)

        weekly_rets = risk_metrics.weekly_returns(closes)
        asset_beta = (
            risk_metrics.beta(weekly_rets, bench_rets)
            if bench_rets is not None else None
        )
        

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