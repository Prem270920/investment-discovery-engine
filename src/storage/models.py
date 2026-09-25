"""
SQLAlchemy ORM models

Two tables:
  * Asset  — one row per ticker (upsert-by-symbol on each run)
  * Price  — daily OHLCV bars (insert-new-dates-only)

The Price.symbol -> Asset.symbol foreign key enforces referential integrity
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    Integer,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.storage.database import Base

# Forecast lenses. Plain strings rather than an Enum type so SQLite and a
# later Postgres move store them the same way.
ARIMA_LENS = "arima"
GRU_LENS = "gru"

# gru_status before any GRU stage has touched the row.
GRU_NOT_RUN = "not_run"

class Asset(Base):
    __tablename__ = "assets"

    # symbol is the natural primary key
    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    short_name: Mapped[str] = mapped_column(String, nullable=False)
    quote_type: Mapped[str] = mapped_column(String, nullable=False)   # ETF / EQUITY
    currency: Mapped[str] = mapped_column(String, nullable=False)     # AUD / USD
    listed_exchange: Mapped[str] = mapped_column(String, nullable=False)   # ASX / US
    underlying_market: Mapped[str] = mapped_column(String, nullable=False)  # AU/US/GLOBAL

    # Nullable fields
    sector: Mapped[str | None] = mapped_column(String, nullable=True)
    # ETF equivalent of sector — 'Long Government', 'Equity Energy', etc.
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trailing_pe: Mapped[float | None] = mapped_column(Float, nullable=True)

    latest_close: Mapped[float] = mapped_column(Float, nullable=False)

    # True for reference series (^AXJO, ^GSPC) used only for beta computation.
    # These are stored like assets (so their price bars satisfy the prices FK)
    # but filtered out of anything a user browses.
    is_benchmark: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # ORM convenience: asset.prices gives all price bars for this asset.
    # cascade so deleting an asset cleans up its orphaned prices.
    prices: Mapped[list["Price"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Asset {self.symbol} ({self.quote_type}, {self.underlying_market})>"
    
class Price(Base):
    __tablename__ = "prices"

    # Surrogate integer PK
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    symbol: Mapped[str] = mapped_column(
        String, ForeignKey("assets.symbol"), nullable=False, index=True
    )
    date: Mapped["Date"] = mapped_column(Date, nullable=False)

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)

    asset: Mapped["Asset"] = relationship(back_populates="prices")

    # A double-run or bug CANNOT create duplicates
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_symbol_date"),)

    def __repr__(self) -> str:
        return f"<Price {self.symbol} {self.date} close={self.close}>"
    
class Forecast(Base):
    """A stored forecast point for one asset on one future date.

    A forecast is a TIME SERIES per asset (one row per future trading day)
    """
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(
        String, ForeignKey("assets.symbol"), nullable=False, index=True
    )
    date: Mapped["Date"] = mapped_column(Date, nullable=False)

    # Which model produced this path. The default keeps older ARIMA-only
    # writers valid without them having to know the column exists.
    lens: Mapped[str] = mapped_column(
        String, nullable=False, default=ARIMA_LENS, server_default=ARIMA_LENS
    )

    predicted: Mapped[float] = mapped_column(Float, nullable=False)
    lower: Mapped[float] = mapped_column(Float, nullable=False)   # 95% CI lower
    upper: Mapped[float] = mapped_column(Float, nullable=False)   # 95% CI upper

    asset: Mapped["Asset"] = relationship()

    __table_args__ = (
        # One point per model per day, so ARIMA and GRU can share a date.
        UniqueConstraint("symbol", "lens", "date", name="uq_forecast_symbol_lens_date"),
        CheckConstraint(f"lens IN ('{ARIMA_LENS}', '{GRU_LENS}')", name="ck_forecast_lens"),
    )


class ForecastMeta(Base):
    """One row per asset summarising its forecast run: which model won the
    backtest, and how wrong it was on held-out data.
    """
    __tablename__ = "forecast_meta"

    symbol: Mapped[str] = mapped_column(
        String, ForeignKey("assets.symbol"), primary_key=True
    )
    method: Mapped[str] = mapped_column(String, nullable=False)      # 'returns' | 'price'
    arima_order: Mapped[str] = mapped_column(String, nullable=False)  # e.g. '(2,1,1)'
    backtest_error_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # GRU side of the comparison. The ARIMA columns above stay the row's
    # identity; these are filled in afterwards and may never be if torch is
    # missing, which is why the status defaults to a value saying so.
    gru_rmse_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gru_status: Mapped[str] = mapped_column(
        String, nullable=False, default=GRU_NOT_RUN, server_default=GRU_NOT_RUN
    )  # 'not_run' | 'ok' | 'skipped_no_torch' | 'failed'
    head_to_head_winner: Mapped[str | None] = mapped_column(String, nullable=True)  # 'arima' | 'gru'

    computed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    asset: Mapped["Asset"] = relationship()
    
class AssetDescription(Base):
    """A beginner-friendly description for one asset, derived from source text"""
    __tablename__ = "asset_descriptions"

    symbol: Mapped[str] = mapped_column(
        String, ForeignKey("assets.symbol"), primary_key=True
    )

    method: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)

    # A JSON column rather than its own table: it's a small, read-only,
    # one-to-one attachment, not relational data with its own identity.
    jargon: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON-encoded

    source_readability: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary_readability: Mapped[float | None] = mapped_column(Float, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    asset: Mapped["Asset"] = relationship()

class AssetMetric(Base):
    """Computed risk metrics for one asset in separate table — recomputed each ingestion run.

    `beta` here is OUR computed beta (covariance / benchmark variance)
    """
    __tablename__ = "asset_metrics"

    symbol: Mapped[str] = mapped_column(String, ForeignKey("assets.symbol"), primary_key=True)

    annualized_volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_symbol: Mapped[str | None] = mapped_column(String, nullable=True)

    # Clustering output — recomputed each run.
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cluster_label: Mapped[str | None] = mapped_column(String, nullable=True)

    # Risk tier — quantile-based (quintile) bucket of annualized volatility across the universe, computed each run
    risk_tier: Mapped[str | None] = mapped_column(String, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    asset: Mapped["Asset"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<AssetMetric {self.symbol} vol={self.annualized_volatility} "
            f"sharpe={self.sharpe_ratio} beta={self.beta} vs {self.benchmark_symbol}>"
        )