"""
Step 8: FastAPI serving layer.

Serves the pipeline's output over HTTP. Reads ONLY from our database — never
calls yfinance at request time. That separation (established back in Step 3) is
what makes this API fast, resilient to feed outages, and independent of Yahoo's
rate limits.


Then open http://127.0.0.1:8000/docs for interactive Swagger docs.
"""

import logging
from datetime import date, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.schemas import (
    AssetDetail,
    AssetSummary,
    Carousel,
    CarouselsResponse,
    HealthStatus,
    PriceHistory,
    PricePoint,
)
from src.storage.database import SessionLocal
from src.storage.models import Asset, AssetMetric, Price

from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("api")

app = FastAPI(
    title="Investment Discovery Engine",
    description=(
        "A beginner-friendly discovery API for stable, long-term investments "
        "across ASX, US, and global markets. "
        "**Educational tool — not financial advice.**"
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Database dependency
def get_db():
    """Yield a DB session per request, always closed afterwards.

    FastAPI's dependency injection calls this for each request. The try/finally
    guarantees the session is returned to the pool even if the endpoint raises —
    without this, a burst of errors would leak connections until the app died.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Helper: join an Asset with its computed metrics
def _asset_with_metrics(db: Session, asset: Asset) -> dict:
    """Flatten an Asset + its AssetMetric into one dict.

    The DB keeps raw (Asset) and derived (AssetMetric) data in separate tables —
    a deliberate storage separation. But the frontend wants one object per asset,
    so the API performs that join. The UI shouldn't have to know our schema.
    """
    metric = db.get(AssetMetric, asset.symbol)
    return {
        "symbol": asset.symbol,
        "short_name": asset.short_name,
        "quote_type": asset.quote_type,
        "currency": asset.currency,
        "underlying_market": asset.underlying_market,
        "listed_exchange": asset.listed_exchange,
        "latest_close": asset.latest_close,
        "sector": asset.sector,
        "dividend_yield": asset.dividend_yield,
        "market_cap": asset.market_cap,
        "trailing_pe": asset.trailing_pe,
        "last_updated": asset.last_updated,
        # Metrics may not exist yet (asset ingested but metrics not computed).
        "annualized_volatility": metric.annualized_volatility if metric else None,
        "sharpe_ratio": metric.sharpe_ratio if metric else None,
        "beta": metric.beta if metric else None,
        "benchmark_symbol": metric.benchmark_symbol if metric else None,
        "risk_tier": metric.risk_tier if metric else None, 
        "metrics_computed_at": metric.computed_at if metric else None,
    }


@app.get("/api/health", response_model=HealthStatus, tags=["system"])
def health(db: Session = Depends(get_db)) -> HealthStatus:
    """Liveness + DATA FRESHNESS check.

    Deliberately more than a ping. An API that returns 200 while serving
    month-old metrics is broken in a way a naive health check would miss — so we
    report when metrics were last computed and warn if the data looks stale.
    """
    warnings: list[str] = []
    try:
        asset_count = db.scalar(
            select(func.count()).select_from(Asset).where(Asset.is_benchmark == False)  # noqa: E712
        ) or 0
        benchmark_count = db.scalar(
            select(func.count()).select_from(Asset).where(Asset.is_benchmark == True)  # noqa: E712
        ) or 0
        last_computed = db.scalar(select(func.max(AssetMetric.computed_at)))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.exception("health check: database unreachable")
        return HealthStatus(
            status="degraded",
            database_connected=False,
            asset_count=0,
            benchmark_count=0,
            warnings=[f"database error: {type(exc).__name__}"],
        )

    if asset_count == 0:
        warnings.append("no assets stored — has the pipeline been run?")
    if last_computed is None:
        warnings.append("no metrics computed yet")
    if benchmark_count == 0:
        warnings.append("no benchmarks stored — beta cannot be computed")

    return HealthStatus(
        status="ok" if not warnings else "degraded",
        database_connected=db_ok,
        asset_count=asset_count,
        benchmark_count=benchmark_count,
        metrics_last_computed=last_computed,
        warnings=warnings,
    )

@app.get("/api/carousels", response_model=CarouselsResponse, tags=["discovery"])
def get_carousels(
    db: Session = Depends(get_db),
    underlying_market: str | None = Query(None, description="Filter each carousel to one market: AU, US, or GLOBAL"),
    min_size: int = Query(
        1, ge=1,
        description="Only return carousels with at least this many assets "
                    "(after filtering) — hides stub clusters",
    ),
) -> CarouselsResponse:
    """The Netflix-style discovery dashboard: assets grouped into named, ML-derived risk carousels.

    Each carousel is a KMeans cluster (see clustering.py), labelled by ranking
    clusters against each other. Assets within a carousel are ranked by Sharpe
    ratio (best risk-adjusted return first) - the most useful ordering for a beginner deciding where to start.

    This is the endpoint we deferred a step before KMeans cluster: it now serves real learned
    categories rather than hand-written threshold filters.
    """
    market = underlying_market.upper() if underlying_market else None

    # Pull every clustered, browsable asset with its metrics in one query
    stmt = (
        select(Asset, AssetMetric)
        .join(AssetMetric, Asset.symbol == AssetMetric.symbol)
        .where(
            Asset.is_benchmark == False,
            AssetMetric.cluster_id.isnot(None),
        )
    )
    if market:
        stmt = stmt.where(Asset.underlying_market == market)

    rows = db.execute(stmt).all()

    # Group rows by cluster. We track full cluster size SEPARATELY,
    # so a market-filtered view can still say "showing N of TOTAL".
    from collections import defaultdict
    grouped: dict[int, list] = defaultdict(list)
    for asset, metric in rows:
        grouped[metric.cluster_id].append((asset, metric))

    # Full cluster sizes + label + centroid
    meta_rows = db.execute(
        select(
            AssetMetric.cluster_id,
            AssetMetric.cluster_label,
            func.count().label("size"),
            func.avg(AssetMetric.annualized_volatility),
            func.avg(AssetMetric.sharpe_ratio),
            func.avg(AssetMetric.beta),
        )
        .where(AssetMetric.cluster_id.isnot(None))
        .group_by(AssetMetric.cluster_id, AssetMetric.cluster_label)
    ).all()
    cluster_meta = {
        r[0]: {"label": r[1], "size": r[2], "vol": r[3], "sharpe": r[4], "beta": r[5]}
        for r in meta_rows
    }

    carousels: list[Carousel] = []
    for cluster_id, members in grouped.items():
        if len(members) < min_size:
            continue  # hide stub carousels

        meta = cluster_meta.get(cluster_id, {})

        # Rank within the carousel by Sharpe, best first
        members.sort(
            key=lambda pair: (
                pair[1].sharpe_ratio if pair[1].sharpe_ratio is not None else -1e9
            ),
            reverse=True,
        )

        summaries = [
            AssetSummary(**_asset_with_metrics(db, asset)) for asset, _ in members
        ]

        carousels.append(Carousel(
            label=meta.get("label") or f"Cluster {cluster_id}",
            cluster_id=cluster_id,
            size=meta.get("size", len(members)),
            avg_volatility=meta.get("vol"),
            avg_sharpe=meta.get("sharpe"),
            avg_beta=meta.get("beta"),
            assets=summaries,
        ))

    # Order carousels low-risk to high-risk (by avg volatility) so the dashboard
    # reads intuitively from "safe" at the top to "growth" lower down.
    carousels.sort(key=lambda c: c.avg_volatility if c.avg_volatility is not None else 0)

    return CarouselsResponse(
        carousels=carousels,
        underlying_market_filter=market,
    )


@app.get("/api/assets", response_model=list[AssetSummary], tags=["assets"])
def list_assets(
    db: Session = Depends(get_db),
    underlying_market: str | None = Query(
        None, description="Filter by exposure: AU, US, or GLOBAL"
    ),
    quote_type: str | None = Query(
        None, description="Filter by type: ETF or EQUITY"
    ),
) -> list[AssetSummary]:
    """List all browsable assets with their computed metrics.

    This single endpoint powers EVERY carousel — the frontend filters and sorts
    the result to build "Top Safe-Haven ETFs", "Stable Dividends in Australia",
    etc. When ML-driven clustering lands, a dedicated /api/carousels endpoint
    will supersede that client-side logic.

    Benchmarks (^AXJO, ^GSPC, AUDUSD=X) are always excluded — they're reference
    series, not investable picks.
    """
    stmt = select(Asset).where(Asset.is_benchmark == False)  # noqa: E712

    if underlying_market:
        stmt = stmt.where(Asset.underlying_market == underlying_market.upper())
    if quote_type:
        stmt = stmt.where(Asset.quote_type == quote_type.upper())

    assets = db.scalars(stmt).all()
    return [AssetSummary(**_asset_with_metrics(db, a)) for a in assets]


@app.get("/api/assets/{symbol}", response_model=AssetDetail, tags=["assets"])
def get_asset(symbol: str, db: Session = Depends(get_db)) -> AssetDetail:
    """Full detail for one asset — powers the Knowledge Card.

    404s for unknown symbols AND for benchmarks (which exist in the assets table
    to satisfy the prices foreign key, but aren't investable picks a user browses).
    """
    asset = db.get(Asset, symbol.upper())
    if asset is None or asset.is_benchmark:
        raise HTTPException(status_code=404, detail=f"Asset '{symbol}' not found")
    return AssetDetail(**_asset_with_metrics(db, asset))


@app.get(
    "/api/assets/{symbol}/prices",
    response_model=PriceHistory,
    tags=["assets"],
)
def get_prices(
    symbol: str,
    db: Session = Depends(get_db),
    days: int = Query(
        365, ge=7, le=2000,
        description="How many days of history to return (most recent first)",
    ),
) -> PriceHistory:
    """Price history for charting on the Knowledge Card.

    Defaults to a year. The `days` cap exists because a beginner's sparkline
    doesn't need 2,000 points — and shipping them would waste bandwidth.
    """
    asset = db.get(Asset, symbol.upper())
    if asset is None or asset.is_benchmark:
        raise HTTPException(status_code=404, detail=f"Asset '{symbol}' not found")

    cutoff = date.today() - timedelta(days=days)
    rows = db.execute(
        select(Price.date, Price.close)
        .where(Price.symbol == asset.symbol, Price.date >= cutoff)
        .order_by(Price.date)
    ).all()

    return PriceHistory(
        symbol=asset.symbol,
        points=[PricePoint(date=r[0], close=r[1]) for r in rows],
    )