"""
Tests for the ARIMA pipeline stage (stage 5), focused on the backtest replay
it stores alongside the forward projection.

The ARIMA engine is stubbed, so these run in the fast suite. Each test uses an
in-memory SQLite database built from the real models.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.ml import compute_forecasts as stage
from src.storage.database import Base
from src.storage.models import ARIMA_LENS, GRU_LENS, Asset, Price
from src.storage.repository import get_backtest, get_forecast_meta, replace_backtest

FIRST_PRICE_DAY = date(2025, 1, 1)
PRICE_DAYS = 100


@pytest.fixture
def session():
    scratch_engine = create_engine("sqlite://")
    Base.metadata.create_all(scratch_engine)
    scratch_session = sessionmaker(bind=scratch_engine)()
    scratch_session.add(Asset(
        symbol="AAA", short_name="AAA", quote_type="EQUITY", currency="USD",
        listed_exchange="NYSE", underlying_market="US", latest_close=199.0,
    ))
    scratch_session.flush()
    for offset in range(PRICE_DAYS):
        close = 100.0 + offset
        scratch_session.add(Price(
            symbol="AAA", date=FIRST_PRICE_DAY + timedelta(days=offset),
            open=close, high=close, low=close, close=close, volume=1000,
        ))
    scratch_session.flush()
    yield scratch_session
    scratch_session.close()
    scratch_engine.dispose()


def _stub_engine(monkeypatch, miss_by):
    """An ARIMA engine that guesses the held out closes off by a fixed amount."""
    def fake_forecast(closes):
        held_out = [float(close) for close in closes.iloc[-30:]]
        return {
            "method": "returns", "order": "(1, 0, 0)", "backtest_error_pct": 1.23,
            "horizon": 30, "predicted": [200.0] * 30, "lower": [190.0] * 30, "upper": [210.0] * 30,
            "backtest_actual": held_out,
            "backtest_predicted": [close + miss_by for close in held_out],
        }
    monkeypatch.setattr(stage, "forecast_asset", fake_forecast)


def test_stage_stores_the_arima_replay_on_the_last_30_price_days(session, monkeypatch):
    _stub_engine(monkeypatch, miss_by=2.0)
    assert stage.compute_and_store_forecasts(session) == (1, 0)

    replay = get_backtest(session, "AAA", ARIMA_LENS)
    assert [day.date for day in replay] == [FIRST_PRICE_DAY + timedelta(days=70 + offset) for offset in range(30)]
    assert [day.actual for day in replay] == [170.0 + offset for offset in range(30)]
    assert [day.predicted for day in replay] == [172.0 + offset for offset in range(30)]
    assert get_forecast_meta(session, "AAA").backtest_error_pct == 1.23


def test_rerun_replaces_the_arima_replay_and_leaves_the_gru_one(session, monkeypatch):
    gru_days = [FIRST_PRICE_DAY + timedelta(days=70 + offset) for offset in range(30)]
    replace_backtest(session, "AAA", GRU_LENS, gru_days, [1.0] * 30, [2.0] * 30)
    _stub_engine(monkeypatch, miss_by=2.0)
    stage.compute_and_store_forecasts(session)
    _stub_engine(monkeypatch, miss_by=-3.0)
    stage.compute_and_store_forecasts(session)

    arima_replay = get_backtest(session, "AAA", ARIMA_LENS)
    assert len(arima_replay) == 30
    assert {day.predicted - day.actual for day in arima_replay} == {-3.0}
    assert len(get_backtest(session, "AAA", GRU_LENS)) == 30


def test_held_out_dates_skip_missing_closes_like_the_engines_do():
    trading_days = pd.date_range("2025-01-01", periods=40, freq="B")
    closes = pd.Series(np.arange(40, dtype=float), index=trading_days)
    closes.iloc[-5] = np.nan

    dates = stage.held_out_dates(closes)

    assert len(dates) == 30
    assert trading_days[-5].date() not in dates
    assert dates[0] == trading_days[9].date()
    assert dates[-1] == trading_days[-1].date()
