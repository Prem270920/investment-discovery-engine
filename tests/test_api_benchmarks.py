"""
API tests for the benchmark price endpoint behind the dashboard hero.

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
from src.storage.models import Asset, Price

TODAY = date.today()


def _add_listing(scratch_session, symbol, short_name, is_benchmark, closes_by_age):
    """closes_by_age maps 'days before today' to a close."""
    scratch_session.add(Asset(
        symbol=symbol, short_name=short_name, quote_type="INDEX" if is_benchmark else "EQUITY",
        currency="USD", listed_exchange="SNP", underlying_market="US",
        latest_close=100.0, is_benchmark=is_benchmark,
    ))
    scratch_session.flush()
    for days_ago, close in closes_by_age.items():
        scratch_session.add(Price(
            symbol=symbol, date=TODAY - timedelta(days=days_ago),
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
    _add_listing(seeding_session, "^GSPC", "S&P 500", True, {400: 4000.0, 30: 5000.0, 2: 5100.0, 1: 5150.0})
    _add_listing(seeding_session, "AAPL", "Apple Inc.", False, {1: 200.0})
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


def test_serves_stored_benchmark_prices_oldest_first_with_name(client):
    response = client.get("/api/benchmarks/%5EGSPC/prices")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "^GSPC"
    assert body["name"] == "S&P 500"
    # The default year leaves out the 400 day old bar.
    assert body["points"] == [
        {"date": (TODAY - timedelta(days=30)).isoformat(), "close": 5000.0},
        {"date": (TODAY - timedelta(days=2)).isoformat(), "close": 5100.0},
        {"date": (TODAY - timedelta(days=1)).isoformat(), "close": 5150.0},
    ]


def test_days_narrows_the_window(client):
    body = client.get("/api/benchmarks/%5EGSPC/prices?days=7").json()
    assert [point["close"] for point in body["points"]] == [5100.0, 5150.0]


def test_symbol_is_case_insensitive(client):
    assert client.get("/api/benchmarks/%5Egspc/prices").json()["symbol"] == "^GSPC"


def test_investable_assets_are_not_served_as_benchmarks(client):
    assert client.get("/api/benchmarks/AAPL/prices").status_code == 404


def test_unknown_symbol_is_404(client):
    assert client.get("/api/benchmarks/%5ENOPE/prices").status_code == 404


def test_asset_prices_endpoint_still_refuses_benchmarks(client):
    # The split is deliberate: benchmarks are context, never picks.
    assert client.get("/api/assets/%5EGSPC/prices").status_code == 404
