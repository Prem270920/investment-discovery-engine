"""
Pydantic response models — the API contract

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
    """Full asset record — what the Knowledge Card needs.
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


class HealthStatus(BaseModel):
    """Liveness + data-freshness check"""
    status: str                  
    database_connected: bool
    asset_count: int
    benchmark_count: int
    metrics_last_computed: datetime | None = None
    warnings: list[str] = []


class Carousel(BaseModel):
    """One themed row in the Netflix-style UI — a cluster, surfaced as a "carousel" of assets."""
    label: str
    cluster_id: int
    size: int
    avg_volatility: float | None = None
    avg_sharpe: float | None = None
    avg_beta: float | None = None
    assets: list[AssetSummary] # ranked, best Sharpe first


class CarouselsResponse(BaseModel):
    """The full set of carousels — the discovery dashboard payload."""
    carousels: list[Carousel]
    underlying_market_filter: str | None = None  # echoes any filter applied