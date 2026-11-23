"""
Pydantic response models: the API contract

These are deliberately separate from the SQLAlchemy models. The DB schema is an
internal implementation detail; the API contract is a public promise. Keeping
them apart means we can change storage without silently breaking clients.

the DB stores Asset and AssetMetric as separate tables (raw vs derived data), but the frontend wants ONE
object per asset. The API is where that join happens, so the UI doesn't have to.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class AssetSummary(BaseModel):
    """Compact asset record - what the Knowledge Card needs for the summary view."""
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    short_name: str
    quote_type: str            # ETF | EQUITY
    currency: str              # AUD | USD
    underlying_market: str     # AU | US | GLOBAL
    latest_close: float

    # Computed metrics
    annualized_volatility: float | None = None
    sharpe_ratio: float | None = None
    beta: float | None = None
    benchmark_symbol: str | None = None
    risk_tier: str | None = None


class AssetDetail(AssetSummary):
    """Full asset record: what the Knowledge Card needs.
    This is the union of the Asset and AssetMetric tables, plus some computed fields.
    """
    listed_exchange: str 
    sector: str | None = None
    dividend_yield: float | None = None
    market_cap: int | None = None
    trailing_pe: float | None = None

    last_updated: datetime | None = None
    metrics_computed_at: datetime | None = None


class PricePoint(BaseModel):
    """One point on a price chart."""
    model_config = ConfigDict(from_attributes=True)

    date: date
    close: float


class PriceHistory(BaseModel):
    """A symbol's price series, for charting on the Knowledge Card."""
    symbol: str
    points: list[PricePoint]


class BenchmarkPriceHistory(PriceHistory):
    """A benchmark index's price series, for the dashboard hero. Carries the
    stored display name so the UI never has to hardcode one per symbol."""
    name: str


class Capabilities(BaseModel):
    """Optional features the stored data can currently back, so the UI can
    hide a feature instead of rendering it half empty."""
    neural_forecast: bool = False


class HealthStatus(BaseModel):
    """Liveness + data-freshness check"""
    status: str                  
    database_connected: bool
    asset_count: int
    benchmark_count: int
    metrics_last_computed: datetime | None = None
    warnings: list[str] = []
    capabilities: Capabilities = Capabilities()


class CarouselAsset(AssetSummary):
    """An asset as it appears on a dashboard card. Adds a thinned price
    series for the card's hover sparkline, so the dashboard doesn't need one
    prices request per card. Only the carousels endpoint carries it; every
    other AssetSummary payload is unchanged."""
    # About 30 evenly spaced closes from the last 63 stored trading days,
    # oldest first. Null when fewer than two prices are stored.
    sparkline_closes: list[float] | None = None


class Carousel(BaseModel):
    """One themed row in the Netflix-style UI: a cluster, surfaced as a "carousel" of assets."""
    label: str
    cluster_id: int
    size: int
    avg_volatility: float | None = None
    avg_sharpe: float | None = None
    avg_beta: float | None = None
    assets: list[CarouselAsset] # ranked, best Sharpe first


class CarouselsResponse(BaseModel):
    """The full set of carousels: the discovery dashboard payload."""
    carousels: list[Carousel]
    underlying_market_filter: str | None = None  # echoes any filter applied

class ForecastPoint(BaseModel):
    """One projected day: central estimate plus its uncertainty band"""
    model_config = ConfigDict(from_attributes=True)

    date: date
    predicted: float
    lower: float
    upper: float


class LensPathPoint(BaseModel):
    """One day of a lens's central projection."""
    date: date
    predicted: float


class LensBandPoint(BaseModel):
    """One day of a lens's uncertainty band."""
    date: date
    lower: float
    upper: float


class ForecastLens(BaseModel):
    """One model's projection, split into the line and the band so the chart
    can draw each without unpicking the other."""
    path: list[LensPathPoint]
    band: list[LensBandPoint]
    rmse_pct: float | None


class ForecastLenses(BaseModel):
    arima: ForecastLens
    # Null unless the GRU stage finished for this asset, so the UI has one
    # thing to check before offering the comparison.
    gru: ForecastLens | None = None


class HeadToHead(BaseModel):
    """Both lenses scored on the same held out days. Fields are null when
    there is no GRU result to compare against."""
    winner: str | None = None             # 'arima' | 'gru'
    arima_rmse_pct: float | None = None
    gru_rmse_pct: float | None = None
    margin_pct_points: float | None = None  # gap between the two errors, always >= 0
    holdout_days: int


class ForecastResponse(BaseModel):
    """A stored ARIMA projection with its measured accuracy.

    The top level fields are the original ARIMA contract and stay as they
    were; lenses and head_to_head were added alongside for the GRU comparison.
    """
    symbol: str
    method: str                    
    arima_order: str
    backtest_error_pct: float | None
    horizon_days: int
    points: list[ForecastPoint]
    lenses: ForecastLenses
    head_to_head: HeadToHead

class JargonTerm(BaseModel):
    """One glossed term from an asset's description."""
    term: str
    plain: str


class AssetDescriptionResponse(BaseModel):
    """A beginner-friendly description derived from source text.

    method tells the UI how to present it:
        'summary' -> extractive summary of a long equity description
        'jargon'  -> the original short ETF text, with terms glossed

    the UI leads with the text, not the numbersreadability score isn't decision-relevant to someone choosing an investment.
    """
    symbol: str
    method: str
    summary: str
    jargon: list[JargonTerm] = []
    source_readability: float | None = None
    summary_readability: float | None = None