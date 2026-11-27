"""
Step 8: FastAPI serving layer.

Serves the pipeline's output over HTTP. Reads ONLY from our database, never
calls yfinance at request time. That separation (established back in Step 3) is
what makes this API fast, resilient to feed outages, and independent of Yahoo's
rate limits.


Then open http://127.0.0.1:8000/docs for interactive Swagger docs.
"""

import logging
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.schemas import (
    AssetDescriptionResponse,
    AssetDetail,
    AssetSummary,
    BacktestReplay,
    BenchmarkPriceHistory,
    Capabilities,
    Carousel,
    CarouselAsset,
    CarouselsResponse,
    ForecastLens,
    ForecastLenses,
    ForecastPoint,
    ForecastResponse,
    HeadToHead,
    HealthStatus,
    JargonTerm,
    LensBandPoint,
    LensPathPoint,
    PriceHistory,
    PricePoint,
)
from src.storage.models import (
    ARIMA_LENS, GRU_LENS, Asset, AssetDescription, AssetMetric, BacktestPrediction, Forecast,
    ForecastMeta, Price,
)
from src.config import CORS_ORIGINS, DATABASE_PATH, FRONTEND_DIST, LOG_LEVEL
from src.storage.database import SessionLocal

from fastapi.middleware.cors import CORSMiddleware

# uvicorn sets up its own loggers but not the root one, so without this the
# app's warnings would only reach the console through Python's last resort.
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("api")

# Mirrors forecasting.BACKTEST_DAYS and compute_neural_forecasts.GRU_OK.
# Copied rather than imported so the API never loads statsmodels or torch;
# a test fails if either drifts.
HOLDOUT_DAYS = 30
GRU_STATUS_OK = "ok"

# Card sparklines: the last 63 trading days (about three months), thinned
# to 30 points. The card's caption says "in 3 months", so the two move together.
SPARKLINE_WINDOW = 63
SPARKLINE_POINTS = 30

app = FastAPI(
    title="Investment Discovery Engine",
    description=(
        "A beginner-friendly discovery API for stable, long-term investments "
        "across ASX, US, and global markets. "
        "**Educational tool, not financial advice.**"
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    # Only needed when the page comes from another address, like the Vite
    # dev server. The built frontend served below shares the API's address.
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Database dependency
def get_db():
    """Yield a DB session per request, always closed afterwards.

    FastAPI's dependency injection calls this for each request. The try/finally
    guarantees the session is returned to the pool even if the endpoint raises;
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

    The DB keeps raw (Asset) and derived (AssetMetric) data in separate tables,
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


def _sparkline_closes(db: Session, symbols: list[str]) -> dict[str, list[float]]:
    """About SPARKLINE_POINTS evenly spaced closes from each symbol's last
    SPARKLINE_WINDOW stored bars, oldest first.

    Thinning keeps the shape of three months of moves while sending a
    fraction of the numbers; a card is too small to show more anyway. The
    first and last kept closes are always the window's first and last, so
    the line starts and ends where the real prices do. Symbols with fewer
    than two stored closes are left out, since one point is not a line.
    """
    if not symbols:
        return {}
    newest_first = (
        func.row_number()
        .over(partition_by=Price.symbol, order_by=Price.date.desc())
        .label("bars_back")
    )
    recent = (
        select(Price.symbol, Price.date, Price.close, newest_first)
        .where(Price.symbol.in_(symbols))
        .subquery()
    )
    rows = db.execute(
        select(recent.c.symbol, recent.c.close)
        .where(recent.c.bars_back <= SPARKLINE_WINDOW)
        .order_by(recent.c.symbol, recent.c.date)
    ).all()

    window_closes: dict[str, list[float]] = {}
    for symbol, close in rows:
        window_closes.setdefault(symbol, []).append(close)

    thinned: dict[str, list[float]] = {}
    for symbol, closes in window_closes.items():
        if len(closes) < 2:
            continue
        if len(closes) <= SPARKLINE_POINTS:
            thinned[symbol] = closes
            continue
        last = len(closes) - 1
        picks = [round(step * last / (SPARKLINE_POINTS - 1)) for step in range(SPARKLINE_POINTS)]
        thinned[symbol] = [closes[pick] for pick in picks]
    return thinned


@app.get("/api/health", response_model=HealthStatus, tags=["system"])
def health(db: Session = Depends(get_db)) -> HealthStatus:
    """Liveness + DATA FRESHNESS check.

    Deliberately more than a ping. An API that returns 200 while serving
    month-old metrics is broken in a way a naive health check would miss, so we
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
        # Judged from stored results, not from whether torch imports here:
        # the API serves what the pipeline wrote and never runs the GRU itself.
        neural_forecast_ready = db.scalar(
            select(func.count()).select_from(ForecastMeta)
            .where(ForecastMeta.gru_status == GRU_STATUS_OK)
        ) > 0
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
        warnings.append("no assets stored: has the pipeline been run?")
    if last_computed is None:
        warnings.append("no metrics computed yet")
    if benchmark_count == 0:
        warnings.append("no benchmarks stored, so beta cannot be computed")

    return HealthStatus(
        status="ok" if not warnings else "degraded",
        database_connected=db_ok,
        asset_count=asset_count,
        benchmark_count=benchmark_count,
        metrics_last_computed=last_computed,
        warnings=warnings,
        capabilities=Capabilities(neural_forecast=neural_forecast_ready),
    )

@app.get("/api/carousels", response_model=CarouselsResponse, tags=["discovery"])
def get_carousels(
    db: Session = Depends(get_db),
    underlying_market: str | None = Query(None, description="Filter each carousel to one market: AU, US, or GLOBAL"),
    min_size: int = Query(
        1, ge=1,
        description="Only return carousels with at least this many assets "
                    "(after filtering), which hides stub clusters",
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

    # One query for every card's sparkline rather than one per asset.
    sparklines = _sparkline_closes(db, [asset.symbol for asset, _ in rows])

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
            CarouselAsset(
                **_asset_with_metrics(db, asset),
                sparkline_closes=sparklines.get(asset.symbol),
            )
            for asset, _ in members
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

    This single endpoint powers EVERY carousel: the frontend filters and sorts
    the result to build "Top Safe-Haven ETFs", "Stable Dividends in Australia",
    etc. When ML-driven clustering lands, a dedicated /api/carousels endpoint
    will supersede that client-side logic.

    Benchmarks (^AXJO, ^GSPC, AUDUSD=X) are always excluded because they're reference
    series, not investable picks.
    """
    stmt = select(Asset).where(Asset.is_benchmark == False)  # noqa: E712

    if underlying_market:
        stmt = stmt.where(Asset.underlying_market == underlying_market.upper())
    if quote_type:
        stmt = stmt.where(Asset.quote_type == quote_type.upper())

    assets = db.scalars(stmt).all()
    return [AssetSummary(**_asset_with_metrics(db, a)) for a in assets]

@app.get("/api/assets/search", response_model=list[AssetSummary], tags=["discovery"])
def search_assets(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=1, description="Search text: symbol or name"),
    limit: int = Query(8, ge=1, le=20),
) -> list[AssetSummary]:
    """Search browsable assets by symbol or name. Case-insensitive substring match on both fields."""
    term = q.strip().lower()

    # Pull candidates matching either field, benchmarks excluded
    stmt = select(Asset).where(
        Asset.is_benchmark == False,  # noqa: E712
        (func.lower(Asset.symbol).contains(term))
        | (func.lower(Asset.short_name).contains(term)),
    )
    candidates = db.scalars(stmt).all()

    def rank(asset: Asset):
        symbol = asset.symbol.lower()
        name = asset.short_name.lower()
        # Lower sort key = higher rank.
        if symbol == term:
            score = 0                      # exact ticker
        elif symbol.startswith(term):
            score = 1                      # ticker prefix
        elif term in symbol:
            score = 2                      # ticker substring
        elif name.startswith(term):
            score = 3                      # name prefix
        else:
            score = 4                      # name substring
        return (score, len(asset.symbol))

    ranked = sorted(candidates, key=rank)[:limit]
    return [AssetSummary(**_asset_with_metrics(db, a)) for a in ranked]

@app.get("/api/assets/{symbol}/related", response_model=list[AssetSummary], tags=["discovery"])
def get_related_assets(
    symbol: str,
    db: Session = Depends(get_db),
    n: int = Query(6, ge=1, le=12),
) -> list[AssetSummary]:
    """Assets related to this one: same sector/category, ranked by how similarly
    they behave. The 'more like this' recommendation.

    404 if the asset itself doesn't exist; an empty list is valid (a unique
    asset with no close peers).
    """
    from src.ml.recommendations import get_related

    asset = db.get(Asset, symbol.upper())
    if asset is None or asset.is_benchmark:
        raise HTTPException(status_code=404, detail=f"Asset '{symbol}' not found")

    related_symbols = get_related(db, asset.symbol, n=n)
    related = [db.get(Asset, s) for s in related_symbols]
    return [AssetSummary(**_asset_with_metrics(db, a)) for a in related if a]


@app.get("/api/assets/{symbol}", response_model=AssetDetail, tags=["assets"])
def get_asset(symbol: str, db: Session = Depends(get_db)) -> AssetDetail:
    """Full detail for one asset, which powers the Knowledge Card.

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
    doesn't need 2,000 points, and shipping them would waste bandwidth.
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

@app.get(
    "/api/benchmarks/{symbol}/prices",
    response_model=BenchmarkPriceHistory,
    tags=["benchmarks"],
)
def get_benchmark_prices(
    symbol: str,
    db: Session = Depends(get_db),
    days: int = Query(
        365, ge=7, le=2000,
        description="How many days of history to return",
    ),
) -> BenchmarkPriceHistory:
    """Stored price history for a benchmark index (^GSPC, ^AXJO, ...).

    The asset prices endpoint deliberately refuses benchmarks so they never
    show up as investable picks; this route serves them only as context. It
    reads stored rows and never calls out to a data feed.
    """
    benchmark = db.get(Asset, symbol.upper())
    if benchmark is None or not benchmark.is_benchmark:
        raise HTTPException(status_code=404, detail=f"Benchmark '{symbol}' not found")

    cutoff = date.today() - timedelta(days=days)
    rows = db.execute(
        select(Price.date, Price.close)
        .where(Price.symbol == benchmark.symbol, Price.date >= cutoff)
        .order_by(Price.date)
    ).all()

    return BenchmarkPriceHistory(
        symbol=benchmark.symbol,
        name=benchmark.short_name,
        points=[PricePoint(date=row[0], close=row[1]) for row in rows],
    )


@app.get(
    "/api/assets/{symbol}/forecast",
    response_model=ForecastResponse,
    tags=["assets"],
)
def get_forecast(symbol: str, db: Session = Depends(get_db)) -> ForecastResponse:
    """Stored ARIMA projection for one asset, with its measured backtest error"""
    asset = db.get(Asset, symbol.upper())
    if asset is None or asset.is_benchmark:
        raise HTTPException(status_code=404, detail=f"Asset '{symbol}' not found")

    meta = db.get(ForecastMeta, asset.symbol)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast available for '{symbol}'",
        )

    arima_rows = _lens_rows(db, asset.symbol, ARIMA_LENS)
    arima_lens = _as_lens(arima_rows, meta.backtest_error_pct)

    gru_lens = None
    if meta.gru_status == GRU_STATUS_OK:
        gru_rows = _lens_rows(db, asset.symbol, GRU_LENS)
        if gru_rows:
            gru_lens = _as_lens(gru_rows, meta.gru_rmse_pct)

    return ForecastResponse(
        symbol=asset.symbol,
        method=meta.method,
        arima_order=meta.arima_order,
        backtest_error_pct=meta.backtest_error_pct,
        horizon_days=meta.horizon_days,
        # ARIMA only: older clients read points as the single forecast line.
        points=[ForecastPoint.model_validate(row) for row in arima_rows],
        lenses=ForecastLenses(arima=arima_lens, gru=gru_lens),
        head_to_head=_head_to_head(meta, gru_lens),
        backtest=_backtest_replay(db, asset.symbol, gru_lens),
    )


def _backtest_rows(db: Session, symbol: str, lens: str) -> list[BacktestPrediction]:
    return list(db.scalars(
        select(BacktestPrediction)
        .where(BacktestPrediction.symbol == symbol, BacktestPrediction.lens == lens)
        .order_by(BacktestPrediction.date)
    ).all())


def _backtest_replay(db: Session, symbol: str, gru_lens: ForecastLens | None) -> BacktestReplay | None:
    arima_days = _backtest_rows(db, symbol, ARIMA_LENS)
    if not arima_days:
        return None
    held_out_dates = [day.date for day in arima_days]

    # GRU joins the replay only when its forward lens is served, and only if
    # it was scored on the very same days; anything else would race two
    # models over different ground.
    gru_path = None
    if gru_lens is not None:
        gru_days = _backtest_rows(db, symbol, GRU_LENS)
        if [day.date for day in gru_days] == held_out_dates:
            gru_path = [day.predicted for day in gru_days]

    return BacktestReplay(
        dates=held_out_dates,
        actual=[day.actual for day in arima_days],
        arima=[day.predicted for day in arima_days],
        gru=gru_path,
    )


def _lens_rows(db: Session, symbol: str, lens: str) -> list[Forecast]:
    return list(db.scalars(
        select(Forecast)
        .where(Forecast.symbol == symbol, Forecast.lens == lens)
        .order_by(Forecast.date)
    ).all())


def _as_lens(rows: list[Forecast], rmse_pct: float | None) -> ForecastLens:
    return ForecastLens(
        path=[LensPathPoint(date=row.date, predicted=row.predicted) for row in rows],
        band=[LensBandPoint(date=row.date, lower=row.lower, upper=row.upper) for row in rows],
        rmse_pct=rmse_pct,
    )


def _head_to_head(meta: ForecastMeta, gru_lens: ForecastLens | None) -> HeadToHead:
    # Only a GRU result that is actually served counts, so the strip and the
    # chart can never disagree about whether a comparison exists.
    if gru_lens is None:
        return HeadToHead(arima_rmse_pct=meta.backtest_error_pct, holdout_days=HOLDOUT_DAYS)

    margin = None
    if meta.backtest_error_pct is not None and meta.gru_rmse_pct is not None:
        # Both errors are stored to 2 decimals; rounding keeps float noise
        # like 0.30000000000000004 out of the response.
        margin = round(abs(meta.backtest_error_pct - meta.gru_rmse_pct), 2)
    return HeadToHead(
        winner=meta.head_to_head_winner,
        arima_rmse_pct=meta.backtest_error_pct,
        gru_rmse_pct=meta.gru_rmse_pct,
        margin_pct_points=margin,
        holdout_days=HOLDOUT_DAYS,
    )

@app.get(
    "/api/assets/{symbol}/description",
    response_model=AssetDescriptionResponse,
    tags=["assets"],
)
def get_description(symbol: str, db: Session = Depends(get_db)) -> AssetDescriptionResponse:
    """A beginner-friendly description for one asset."""
    import json

    asset = db.get(Asset, symbol.upper())
    if asset is None or asset.is_benchmark:
        raise HTTPException(status_code=404, detail=f"Asset '{symbol}' not found")

    desc = db.get(AssetDescription, asset.symbol)
    if desc is None:
        raise HTTPException(
            status_code=404,
            detail=f"No description available for '{symbol}'",
        )

    jargon = json.loads(desc.jargon) if desc.jargon else []

    return AssetDescriptionResponse(
        symbol=desc.symbol,
        method=desc.method,
        summary=desc.summary,
        jargon=[JargonTerm(**item) for item in jargon],
        source_readability=desc.source_readability,
        summary_readability=desc.summary_readability,
    )


def serve_frontend(api_app: FastAPI, dist_dir: Path) -> bool:
    """Serve the built React app from dist_dir at /, beside the API.

    Any path that isn't an API route and isn't a real file in the build gets
    index.html, so a refreshed or shared link inside the app still loads the
    app. Paths under /api never fall through to the page: an unknown API path
    stays a JSON 404 rather than quietly returning HTML.

    Registered after every API route so those always match first. Without a
    build the API runs on its own and says so once, which is the normal state
    in local development, where Vite serves the page.
    """
    if not (dist_dir / "index.html").is_file():
        logger.warning(
            "no built frontend at %s, so only the API is served; run npm run build in frontend/ to serve the app too",
            dist_dir,
        )
        return False
    build_root = dist_dir.resolve()

    @api_app.get("/{page_path:path}", include_in_schema=False)
    def frontend_page(page_path: str) -> FileResponse:
        if page_path == "api" or page_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if page_path:
            # Resolved and checked, so ../ can never reach outside the build.
            requested_file = (build_root / page_path).resolve()
            if requested_file.is_relative_to(build_root) and requested_file.is_file():
                return FileResponse(requested_file)
        return FileResponse(build_root / "index.html")

    logger.info("serving the built frontend from %s", build_root)
    return True


logger.info("reading the database at %s", DATABASE_PATH)
serve_frontend(app, FRONTEND_DIST)
