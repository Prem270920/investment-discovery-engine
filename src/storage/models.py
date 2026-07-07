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
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.storage.database import Base

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
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    trailing_pe: Mapped[float | None] = mapped_column(Float, nullable=True)

    latest_close: Mapped[float] = mapped_column(Float, nullable=False)

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

    # A double-run or bug CANNOT create duplicates.
    __table_args__ = (
    UniqueConstraint("symbol", "date", name="uq_symbol_date"),)

    def __repr__(self) -> str:
        return f"<Price {self.symbol} {self.date} close={self.close}>"