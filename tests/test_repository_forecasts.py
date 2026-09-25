"""
Tests for storing ARIMA and GRU forecasts side by side.

Each test gets a throwaway in-memory SQLite database built from the real
models, so constraints and server defaults behave as they do in production.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.storage.database import Base
from src.storage.models import (
    ARIMA_LENS,
    GRU_LENS,
    GRU_NOT_RUN,
    Asset,
    Forecast,
    ForecastMeta,
)
from src.storage.repository import (
    get_forecast_meta,
    get_forecast_points,
    replace_forecast,
    update_gru_meta,
    upsert_arima_meta,
)

SYMBOL = "VAS.AX"
FIRST_DAY = date(2026, 9, 28)


@pytest.fixture
def session():
    scratch_engine = create_engine("sqlite://")
    Base.metadata.create_all(scratch_engine)
    scratch_session = sessionmaker(bind=scratch_engine)()
    scratch_session.add(Asset(
        symbol=SYMBOL,
        short_name="Vanguard Australian Shares",
        quote_type="ETF",
        currency="AUD",
        listed_exchange="ASX",
        underlying_market="AU",
        latest_close=100.0,
    ))
    scratch_session.flush()
    yield scratch_session
    scratch_session.close()
    scratch_engine.dispose()


def _projection(days, start_price):
    dates = [FIRST_DAY + timedelta(days=offset) for offset in range(days)]
    mids = [start_price + offset for offset in range(days)]
    return dates, mids, [m - 5 for m in mids], [m + 5 for m in mids]


def test_forecast_written_without_lens_defaults_to_arima(session):
    # This is how compute_forecasts.py still writes rows today.
    session.add(Forecast(symbol=SYMBOL, date=FIRST_DAY, predicted=1.0, lower=0.5, upper=1.5))
    session.flush()
    stored_lens = session.execute(text("SELECT lens FROM forecasts")).scalar_one()
    assert stored_lens == ARIMA_LENS


def test_raw_sql_insert_without_lens_gets_arima_server_default(session):
    session.execute(text(
        "INSERT INTO forecasts (symbol, date, predicted, lower, upper) "
        "VALUES (:symbol, :day, 1.0, 0.5, 1.5)"
    ), {"symbol": SYMBOL, "day": FIRST_DAY})
    assert session.execute(text("SELECT lens FROM forecasts")).scalar_one() == ARIMA_LENS


def test_both_lenses_can_share_a_date(session):
    replace_forecast(session, SYMBOL, *_projection(3, 100.0), lens=ARIMA_LENS)
    replace_forecast(session, SYMBOL, *_projection(3, 200.0), lens=GRU_LENS)
    session.flush()
    assert session.query(Forecast).count() == 6


def test_duplicate_point_within_a_lens_is_rejected(session):
    session.add(Forecast(symbol=SYMBOL, lens=GRU_LENS, date=FIRST_DAY, predicted=1, lower=0, upper=2))
    session.add(Forecast(symbol=SYMBOL, lens=GRU_LENS, date=FIRST_DAY, predicted=1, lower=0, upper=2))
    with pytest.raises(IntegrityError):
        session.flush()


def test_unknown_lens_is_rejected(session):
    session.add(Forecast(symbol=SYMBOL, lens="lstm", date=FIRST_DAY, predicted=1, lower=0, upper=2))
    with pytest.raises(IntegrityError):
        session.flush()


def test_replacing_gru_leaves_arima_rows_alone(session):
    arima_dates, arima_mids, arima_lows, arima_highs = _projection(5, 100.0)
    replace_forecast(session, SYMBOL, arima_dates, arima_mids, arima_lows, arima_highs)
    replace_forecast(session, SYMBOL, *_projection(5, 200.0), lens=GRU_LENS)
    replace_forecast(session, SYMBOL, *_projection(4, 300.0), lens=GRU_LENS)
    session.flush()

    arima_points = get_forecast_points(session, SYMBOL)
    assert [p.predicted for p in arima_points] == arima_mids
    assert [p.lower for p in arima_points] == arima_lows

    gru_points = get_forecast_points(session, SYMBOL, lens=GRU_LENS)
    assert [p.predicted for p in gru_points] == [300.0, 301.0, 302.0, 303.0]


def test_points_come_back_in_date_order(session):
    dates, mids, lows, highs = _projection(4, 100.0)
    replace_forecast(session, SYMBOL, dates[::-1], mids[::-1], lows[::-1], highs[::-1])
    session.flush()
    assert [p.date for p in get_forecast_points(session, SYMBOL)] == dates


def test_mismatched_forecast_columns_are_refused(session):
    dates, mids, lows, highs = _projection(3, 100.0)
    with pytest.raises(ValueError):
        replace_forecast(session, SYMBOL, dates, mids[:2], lows, highs)


def test_meta_created_the_old_way_gets_gru_defaults(session):
    session.add(ForecastMeta(
        symbol=SYMBOL, method="returns", arima_order="(1, 0, 0)",
        backtest_error_pct=2.5, horizon_days=30,
    ))
    session.flush()
    meta = get_forecast_meta(session, SYMBOL)
    assert meta.gru_status == GRU_NOT_RUN
    assert meta.gru_rmse_pct is None
    assert meta.head_to_head_winner is None


def test_gru_update_keeps_arima_summary_intact(session):
    upsert_arima_meta(session, SYMBOL, "price", "(0, 1, 1)", 1.07, 30)
    session.flush()
    assert update_gru_meta(session, SYMBOL, "ok", gru_rmse_pct=0.9, head_to_head_winner=GRU_LENS)
    session.flush()

    meta = get_forecast_meta(session, SYMBOL)
    assert (meta.method, meta.arima_order, meta.backtest_error_pct, meta.horizon_days) == (
        "price", "(0, 1, 1)", 1.07, 30,
    )
    assert (meta.gru_status, meta.gru_rmse_pct, meta.head_to_head_winner) == ("ok", 0.9, GRU_LENS)


def test_arima_rerun_keeps_gru_summary_intact(session):
    upsert_arima_meta(session, SYMBOL, "price", "(0, 1, 1)", 1.07, 30)
    session.flush()
    update_gru_meta(session, SYMBOL, "ok", gru_rmse_pct=0.9, head_to_head_winner=GRU_LENS)
    upsert_arima_meta(session, SYMBOL, "returns", "(2, 0, 0)", 2.03, 30)
    session.flush()

    meta = get_forecast_meta(session, SYMBOL)
    assert (meta.method, meta.arima_order) == ("returns", "(2, 0, 0)")
    assert (meta.gru_status, meta.gru_rmse_pct, meta.head_to_head_winner) == ("ok", 0.9, GRU_LENS)


def test_gru_update_without_arima_summary_is_skipped(session):
    assert update_gru_meta(session, SYMBOL, "skipped_no_torch") is False
    assert get_forecast_meta(session, SYMBOL) is None
