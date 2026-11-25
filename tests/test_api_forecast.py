"""
API tests for the two lens forecast endpoint, its backtest replay, and the
health capabilities.

Each test runs the real FastAPI app against a throwaway in-memory SQLite
database, swapped in through the get_db dependency, so the production
database is never touched.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api import main as api
from src.storage.database import Base
from src.storage.models import ARIMA_LENS, GRU_LENS, Asset
from src.storage.repository import (
    replace_backtest, replace_forecast, update_gru_meta, upsert_arima_meta,
)

FIRST_DAY = date(2026, 11, 23)
ORIGINAL_FORECAST_FIELDS = {
    "symbol", "method", "arima_order", "backtest_error_pct", "horizon_days", "points",
}
# The 30 real trading days before FIRST_DAY that both models were tested on.
HELD_OUT_DAYS = [date(2026, 10, 12) + timedelta(days=offset) for offset in range(30)]
REAL_CLOSES = [150.0 + offset for offset in range(30)]
ARIMA_GUESSES = [151.0 + offset for offset in range(30)]
GRU_GUESSES = [149.5 + offset for offset in range(30)]


def _add_asset(scratch_session, symbol):
    scratch_session.add(Asset(
        symbol=symbol, short_name=symbol, quote_type="EQUITY", currency="USD",
        listed_exchange="NYSE", underlying_market="US", latest_close=100.0,
    ))
    scratch_session.flush()


def _store_projection(scratch_session, symbol, lens, start_price, days=30):
    projection_dates = [FIRST_DAY + timedelta(days=offset) for offset in range(days)]
    mids = [start_price + offset for offset in range(days)]
    replace_forecast(
        scratch_session, symbol, projection_dates, mids,
        [mid - 5 for mid in mids], [mid + 5 for mid in mids], lens=lens,
    )


@pytest.fixture
def scratch_session():
    # StaticPool keeps one connection, so the app's sessions and the test's
    # session all see the same in-memory database.
    scratch_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(scratch_engine)
    session_factory = sessionmaker(bind=scratch_engine)
    seeding_session = session_factory()

    def scratch_db():
        request_session = session_factory()
        try:
            yield request_session
        finally:
            request_session.close()

    api.app.dependency_overrides[api.get_db] = scratch_db
    yield seeding_session
    api.app.dependency_overrides.clear()
    seeding_session.close()
    scratch_engine.dispose()


@pytest.fixture
def client(scratch_session):
    return TestClient(api.app)


@pytest.fixture
def gru_winner(scratch_session):
    """AAPL: GRU finished and beat ARIMA."""
    _add_asset(scratch_session, "AAPL")
    _store_projection(scratch_session, "AAPL", ARIMA_LENS, start_price=200.0)
    _store_projection(scratch_session, "AAPL", GRU_LENS, start_price=300.0)
    replace_backtest(scratch_session, "AAPL", ARIMA_LENS, HELD_OUT_DAYS, REAL_CLOSES, ARIMA_GUESSES)
    replace_backtest(scratch_session, "AAPL", GRU_LENS, HELD_OUT_DAYS, REAL_CLOSES, GRU_GUESSES)
    upsert_arima_meta(scratch_session, "AAPL", "returns", "(1, 0, 0)", 1.46, 30)
    update_gru_meta(scratch_session, "AAPL", "ok", gru_rmse_pct=1.16, head_to_head_winner=GRU_LENS)
    scratch_session.commit()


@pytest.fixture
def too_close(scratch_session):
    """AAPL: both models ran and finished within 0.05 points of each other."""
    _add_asset(scratch_session, "AAPL")
    _store_projection(scratch_session, "AAPL", ARIMA_LENS, start_price=200.0)
    _store_projection(scratch_session, "AAPL", GRU_LENS, start_price=300.0)
    replace_backtest(scratch_session, "AAPL", ARIMA_LENS, HELD_OUT_DAYS, REAL_CLOSES, ARIMA_GUESSES)
    replace_backtest(scratch_session, "AAPL", GRU_LENS, HELD_OUT_DAYS, REAL_CLOSES, GRU_GUESSES)
    upsert_arima_meta(scratch_session, "AAPL", "returns", "(1, 0, 0)", 1.63, 30)
    update_gru_meta(scratch_session, "AAPL", "ok", gru_rmse_pct=1.62, head_to_head_winner="too_close")
    scratch_session.commit()


@pytest.fixture
def gru_skipped(scratch_session):
    """SHY: GRU never ran because torch was unavailable."""
    _add_asset(scratch_session, "SHY")
    _store_projection(scratch_session, "SHY", ARIMA_LENS, start_price=80.0)
    replace_backtest(scratch_session, "SHY", ARIMA_LENS, HELD_OUT_DAYS, REAL_CLOSES, ARIMA_GUESSES)
    upsert_arima_meta(scratch_session, "SHY", "price", "(0, 1, 1)", 0.41, 30)
    update_gru_meta(scratch_session, "SHY", "skipped_no_torch")
    scratch_session.commit()


def test_original_fields_are_unchanged_and_points_stay_arima_only(client, gru_winner):
    forecast_body = client.get("/api/assets/AAPL/forecast").json()

    assert ORIGINAL_FORECAST_FIELDS <= forecast_body.keys()
    assert forecast_body["method"] == "returns"
    assert forecast_body["arima_order"] == "(1, 0, 0)"
    assert forecast_body["backtest_error_pct"] == 1.46
    assert forecast_body["horizon_days"] == 30
    # The GRU rows share these dates; before the lens filter they leaked
    # into points and doubled the line.
    assert len(forecast_body["points"]) == 30
    assert forecast_body["points"][0] == {
        "date": FIRST_DAY.isoformat(), "predicted": 200.0, "lower": 195.0, "upper": 205.0,
    }


def test_both_lenses_are_served_with_path_band_and_rmse(client, gru_winner):
    lenses = client.get("/api/assets/AAPL/forecast").json()["lenses"]

    assert lenses["arima"]["rmse_pct"] == 1.46
    assert lenses["gru"]["rmse_pct"] == 1.16
    assert len(lenses["gru"]["path"]) == len(lenses["gru"]["band"]) == 30
    assert lenses["gru"]["path"][0] == {"date": FIRST_DAY.isoformat(), "predicted": 300.0}
    assert lenses["gru"]["band"][0] == {"date": FIRST_DAY.isoformat(), "lower": 295.0, "upper": 305.0}
    assert lenses["arima"]["path"][0]["predicted"] == 200.0


def test_head_to_head_reports_winner_and_margin(client, gru_winner):
    head_to_head = client.get("/api/assets/AAPL/forecast").json()["head_to_head"]
    assert head_to_head == {
        "winner": "gru",
        "arima_rmse_pct": 1.46,
        "gru_rmse_pct": 1.16,
        "margin_pct_points": 0.3,
        "holdout_days": 30,
    }


def test_head_to_head_passes_through_too_close(client, too_close):
    forecast_body = client.get("/api/assets/AAPL/forecast").json()
    assert forecast_body["head_to_head"] == {
        "winner": "too_close",
        "arima_rmse_pct": 1.63,
        "gru_rmse_pct": 1.62,
        "margin_pct_points": 0.01,
        "holdout_days": 30,
    }
    # A close result is still a full comparison: both lenses and both replays are served.
    assert forecast_body["lenses"]["gru"]["rmse_pct"] == 1.62
    assert forecast_body["backtest"]["gru"] == GRU_GUESSES


def test_too_close_is_dropped_with_the_gru_lens(client, scratch_session, too_close):
    # No served GRU means no comparison, so even a stored verdict is not shown.
    replace_forecast(scratch_session, "AAPL", [], [], [], [], lens=GRU_LENS)
    scratch_session.commit()
    assert client.get("/api/assets/AAPL/forecast").json()["head_to_head"]["winner"] is None


def test_gru_is_null_and_head_to_head_empty_when_not_ok(client, gru_skipped):
    forecast_body = client.get("/api/assets/SHY/forecast").json()

    assert forecast_body["lenses"]["gru"] is None
    assert forecast_body["lenses"]["arima"]["rmse_pct"] == 0.41
    assert forecast_body["head_to_head"] == {
        "winner": None,
        "arima_rmse_pct": 0.41,
        "gru_rmse_pct": None,
        "margin_pct_points": None,
        "holdout_days": 30,
    }
    assert len(forecast_body["points"]) == 30


def test_ok_status_without_stored_rows_is_still_null(client, scratch_session, gru_winner):
    # A status that claims success with no path behind it must not produce a
    # half drawn GRU line.
    replace_forecast(scratch_session, "AAPL", [], [], [], [], lens=GRU_LENS)
    scratch_session.commit()
    forecast_body = client.get("/api/assets/AAPL/forecast").json()
    assert forecast_body["lenses"]["gru"] is None
    assert forecast_body["head_to_head"]["winner"] is None


def test_backtest_serves_both_predictions_beside_the_real_closes(client, gru_winner):
    forecast_body = client.get("/api/assets/AAPL/forecast").json()

    assert set(forecast_body) == ORIGINAL_FORECAST_FIELDS | {"lenses", "head_to_head", "backtest"}
    assert forecast_body["backtest"] == {
        "dates": [day.isoformat() for day in HELD_OUT_DAYS],
        "actual": REAL_CLOSES,
        "arima": ARIMA_GUESSES,
        "gru": GRU_GUESSES,
    }


def test_backtest_gru_is_null_when_the_gru_did_not_run(client, gru_skipped):
    backtest = client.get("/api/assets/SHY/forecast").json()["backtest"]

    assert backtest["gru"] is None
    assert backtest["arima"] == ARIMA_GUESSES
    assert backtest["actual"] == REAL_CLOSES
    assert len(backtest["dates"]) == 30


def test_backtest_gru_is_null_when_its_forward_lens_is_not_served(client, scratch_session, gru_winner):
    # A replay row left behind with no served GRU lens must not show up alone.
    replace_forecast(scratch_session, "AAPL", [], [], [], [], lens=GRU_LENS)
    scratch_session.commit()
    assert client.get("/api/assets/AAPL/forecast").json()["backtest"]["gru"] is None


def test_backtest_gru_is_null_when_stored_before_replays_existed(client, scratch_session, gru_winner):
    replace_backtest(scratch_session, "AAPL", GRU_LENS, [], [], [])
    scratch_session.commit()
    forecast_body = client.get("/api/assets/AAPL/forecast").json()
    assert forecast_body["lenses"]["gru"] is not None
    assert forecast_body["backtest"]["gru"] is None


def test_backtest_gru_is_null_when_scored_on_different_days(client, scratch_session, gru_winner):
    shifted_days = [day + timedelta(days=1) for day in HELD_OUT_DAYS]
    replace_backtest(scratch_session, "AAPL", GRU_LENS, shifted_days, REAL_CLOSES, GRU_GUESSES)
    scratch_session.commit()
    assert client.get("/api/assets/AAPL/forecast").json()["backtest"]["gru"] is None


def test_backtest_is_null_until_the_arima_replay_is_stored(client, scratch_session, gru_winner):
    replace_backtest(scratch_session, "AAPL", ARIMA_LENS, [], [], [])
    scratch_session.commit()
    forecast_body = client.get("/api/assets/AAPL/forecast").json()
    assert forecast_body["backtest"] is None
    # Everything else is served exactly as before.
    assert forecast_body["lenses"]["gru"]["rmse_pct"] == 1.16
    assert forecast_body["head_to_head"]["winner"] == "gru"


def test_unknown_asset_is_404(client, gru_winner):
    assert client.get("/api/assets/NOPE/forecast").status_code == 404


def test_health_reports_neural_forecast_when_a_gru_result_is_stored(client, gru_winner):
    health_body = client.get("/api/health").json()
    assert health_body["capabilities"] == {"neural_forecast": True}


def test_health_reports_no_neural_forecast_when_every_gru_was_skipped(client, gru_skipped):
    health_body = client.get("/api/health").json()
    assert health_body["capabilities"] == {"neural_forecast": False}


def test_api_constants_match_the_pipeline():
    from src.ml.compute_neural_forecasts import GRU_OK
    from src.ml.forecasting import BACKTEST_DAYS

    assert api.HOLDOUT_DAYS == BACKTEST_DAYS
    assert api.GRU_STATUS_OK == GRU_OK
