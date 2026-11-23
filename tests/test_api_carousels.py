"""
API tests for /api/carousels, focused on the card sparkline field added in
Step R3 and on keeping every field that existed before it unchanged.

Runs the real FastAPI app against a throwaway in-memory SQLite database,
swapped in through the get_db dependency.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api import main as api
from src.storage.database import Base
from src.storage.models import Asset, AssetMetric, Price

FIRST_DAY = date(2026, 1, 1)

# Every key a carousel asset carried before the sparkline was added.
PRE_R3_ASSET_KEYS = {
    "symbol", "short_name", "quote_type", "currency", "underlying_market", "latest_close",
    "annualized_volatility", "sharpe_ratio", "beta", "benchmark_symbol", "risk_tier",
}
PRE_R3_CAROUSEL_KEYS = {"label", "cluster_id", "size", "avg_volatility", "avg_sharpe", "avg_beta", "assets"}


def _add_asset(scratch_session, symbol, market, closes, sharpe):
    scratch_session.add(Asset(
        symbol=symbol, short_name=f"{symbol} name", quote_type="ETF", currency="USD",
        listed_exchange="NYSE", underlying_market=market, latest_close=closes[-1] if closes else 1.0,
    ))
    scratch_session.flush()
    scratch_session.add(AssetMetric(
        symbol=symbol, annualized_volatility=0.1, sharpe_ratio=sharpe, beta=0.5,
        benchmark_symbol="^GSPC", cluster_id=0, cluster_label="Safe & Steady", risk_tier="Very low",
    ))
    for offset, close in enumerate(closes):
        scratch_session.add(Price(
            symbol=symbol, date=FIRST_DAY + timedelta(days=offset),
            open=close, high=close, low=close, close=close, volume=0,
        ))


@pytest.fixture
def client():
    scratch_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(scratch_engine)
    session_factory = sessionmaker(bind=scratch_engine)

    seeding_session = session_factory()
    # 120 bars whose close is its own position, so any value names its day.
    _add_asset(seeding_session, "LONG", "US", [float(day) for day in range(120)], sharpe=1.0)
    _add_asset(seeding_session, "SHORT", "US", [10.0, 11.0, 12.0], sharpe=0.5)
    _add_asset(seeding_session, "LONE", "AU", [5.0], sharpe=0.2)
    seeding_session.commit()
    seeding_session.close()

    def scratch_db():
        request_session = session_factory()
        try:
            yield request_session
        finally:
            request_session.close()

    api.app.dependency_overrides[api.get_db] = scratch_db
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    scratch_engine.dispose()


def _assets_by_symbol(body):
    return {asset["symbol"]: asset for carousel in body["carousels"] for asset in carousel["assets"]}


def test_every_pre_r3_field_is_still_present_with_its_value(client):
    body = client.get("/api/carousels").json()
    carousel = body["carousels"][0]
    assert PRE_R3_CAROUSEL_KEYS <= carousel.keys()
    assert [asset["symbol"] for asset in carousel["assets"]] == ["LONG", "SHORT", "LONE"]

    long_asset = _assets_by_symbol(body)["LONG"]
    assert set(long_asset) == PRE_R3_ASSET_KEYS | {"sparkline_closes"}
    assert long_asset["latest_close"] == 119.0
    assert long_asset["sharpe_ratio"] == 1.0
    assert long_asset["risk_tier"] == "Very low"


def test_sparkline_thins_the_last_63_bars_to_30_evenly_spaced_closes(client):
    closes = _assets_by_symbol(client.get("/api/carousels").json())["LONG"]["sparkline_closes"]
    assert len(closes) == 30
    # The window is bars 57..119; it starts and ends exactly there.
    assert closes[0] == 57.0
    assert closes[-1] == 119.0
    assert closes == sorted(closes)
    gaps = {round(later - earlier) for earlier, later in zip(closes, closes[1:])}
    # 62 bars over 29 gaps is 2.14 bars a gap, so rounding gives 2s and the odd 3.
    assert gaps <= {2, 3}


def test_short_history_is_sent_whole_and_a_single_close_is_null(client):
    assets = _assets_by_symbol(client.get("/api/carousels").json())
    assert assets["SHORT"]["sparkline_closes"] == [10.0, 11.0, 12.0]
    assert assets["LONE"]["sparkline_closes"] is None


def test_market_filter_still_applies(client):
    body = client.get("/api/carousels?underlying_market=AU").json()
    assert list(_assets_by_symbol(body)) == ["LONE"]
    assert body["underlying_market_filter"] == "AU"


def test_other_asset_endpoints_do_not_gain_the_field(client):
    for path in ("/api/assets", "/api/assets/search?q=LONG"):
        for asset in client.get(path).json():
            assert "sparkline_closes" not in asset
