"""
Tests for the GRU pipeline stage (stage 5b).

The GRU itself is stubbed out, so these run in the fast suite without torch.
They check what the stage writes: lens "gru" rows, gru_status, gru_rmse_pct
and the head to head winner. Each test uses an in-memory SQLite database
built from the real models.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.ml import compute_neural_forecasts as stage
from src.ml.forecasting import HORIZON_DAYS
from src.storage.database import Base
from src.storage.models import ARIMA_LENS, GRU_LENS, GRU_NOT_RUN, Asset, Forecast, Price
from src.storage.repository import (
    get_backtest, get_forecast_meta, replace_backtest, replace_forecast, upsert_arima_meta,
)

ARIMA_ERRORS = {"AAA": 2.0, "BBB": 1.0, "CCC": 1.5}
FIRST_PRICE_DAY = date(2025, 1, 1)


@pytest.fixture
def session():
    scratch_engine = create_engine("sqlite://")
    Base.metadata.create_all(scratch_engine)
    scratch_session = sessionmaker(bind=scratch_engine)()
    for symbol, arima_error in ARIMA_ERRORS.items():
        scratch_session.add(Asset(
            symbol=symbol, short_name=symbol, quote_type="EQUITY", currency="USD",
            listed_exchange="NYSE", underlying_market="US", latest_close=100.0,
        ))
        scratch_session.flush()
        for offset in range(100):
            close = 100.0 + offset
            scratch_session.add(Price(
                symbol=symbol, date=FIRST_PRICE_DAY + timedelta(days=offset),
                open=close, high=close, low=close, close=close, volume=1000,
            ))
        upsert_arima_meta(scratch_session, symbol, "returns", "(1,0,0)", arima_error, HORIZON_DAYS)
    scratch_session.flush()
    yield scratch_session
    scratch_session.close()
    scratch_engine.dispose()


def _gru_result(error_pct):
    return {
        "method": "gru",
        "backtest_error_pct": error_pct,
        "horizon": HORIZON_DAYS,
        "predicted": [200.0] * HORIZON_DAYS,
        "lower": [190.0] * HORIZON_DAYS,
        "upper": [210.0] * HORIZON_DAYS,
        "backtest_best_epoch": 5,
        "forward_best_epoch": 6,
        # The fixture's last 30 closes are 170 to 199.
        "backtest_actual": [170.0 + offset for offset in range(30)],
        "backtest_predicted": [171.0 + offset for offset in range(30)],
    }


@pytest.fixture
def stub_gru(monkeypatch):
    """GRU beats ARIMA on AAA, loses on BBB, and raises on CCC."""
    def fake_forecast(closes):
        last_close = float(closes.iloc[-1])
        # The fixture gives each symbol the same prices, so key off a counter
        # instead: calls come in symbol order.
        symbol = sorted(ARIMA_ERRORS)[fake_forecast.calls]
        fake_forecast.calls += 1
        assert last_close == 199.0
        if symbol == "CCC":
            raise RuntimeError("boom")
        return _gru_result({"AAA": 1.0, "BBB": 3.0}[symbol])
    fake_forecast.calls = 0
    monkeypatch.setattr(stage, "torch_available", lambda: True)
    monkeypatch.setattr(stage, "forecast_asset_gru", fake_forecast)


def _gru_row_count(session, symbol):
    return session.scalar(
        select(func.count()).select_from(Forecast)
        .where(Forecast.symbol == symbol, Forecast.lens == GRU_LENS)
    )


@pytest.mark.parametrize(("arima", "gru", "winner"), [
    (2.0, 1.0, GRU_LENS),
    (1.0, 2.0, ARIMA_LENS),
    (1.0, 1.0, ARIMA_LENS),  # tie goes to the simpler model
    (None, 1.0, None),
    (1.0, None, None),
])
def test_pick_winner(arima, gru, winner):
    assert stage.pick_winner(arima, gru) == winner


def test_stage_stores_gru_rows_status_and_winner(session, stub_gru):
    counts = stage.compute_and_store_neural_forecasts(session)
    assert counts == {"ok": 2, "failed": 1, "skipped_no_torch": 0}

    winner_meta = get_forecast_meta(session, "AAA")
    assert (winner_meta.gru_status, winner_meta.gru_rmse_pct, winner_meta.head_to_head_winner) == ("ok", 1.0, GRU_LENS)
    loser_meta = get_forecast_meta(session, "BBB")
    assert (loser_meta.gru_status, loser_meta.gru_rmse_pct, loser_meta.head_to_head_winner) == ("ok", 3.0, ARIMA_LENS)
    assert _gru_row_count(session, "AAA") == HORIZON_DAYS
    assert _gru_row_count(session, "BBB") == HORIZON_DAYS


def test_stage_stores_the_gru_replay_on_the_last_30_price_days(session, stub_gru):
    stage.compute_and_store_neural_forecasts(session)
    replay = get_backtest(session, "AAA", GRU_LENS)
    # 100 daily prices from FIRST_PRICE_DAY, so the last 30 start at day 70.
    assert [day.date for day in replay] == [FIRST_PRICE_DAY + timedelta(days=70 + offset) for offset in range(30)]
    assert [day.actual for day in replay] == [170.0 + offset for offset in range(30)]
    assert [day.predicted for day in replay] == [171.0 + offset for offset in range(30)]


def test_one_failing_asset_is_marked_failed_and_others_continue(session, stub_gru):
    replace_forecast(session, "CCC", [date(2025, 6, 2)], [1.0], [0.5], [1.5], lens=GRU_LENS)
    replace_backtest(session, "CCC", GRU_LENS, [date(2025, 3, 1)], [1.0], [1.0])
    stage.compute_and_store_neural_forecasts(session)

    failed_meta = get_forecast_meta(session, "CCC")
    assert (failed_meta.gru_status, failed_meta.gru_rmse_pct, failed_meta.head_to_head_winner) == ("failed", None, None)
    # The stale path and replay from an earlier run are gone, not left beside "failed".
    assert _gru_row_count(session, "CCC") == 0
    assert get_backtest(session, "CCC", GRU_LENS) == []


def test_without_torch_every_asset_is_skipped_with_one_warning(session, monkeypatch, caplog):
    replace_backtest(session, "AAA", GRU_LENS, [date(2025, 3, 1)], [1.0], [1.0])
    monkeypatch.setattr(stage, "torch_available", lambda: False)
    monkeypatch.setattr(stage, "forecast_asset_gru", lambda closes: pytest.fail("GRU must not run"))

    with caplog.at_level("WARNING", logger="compute_neural_forecasts"):
        counts = stage.compute_and_store_neural_forecasts(session)

    assert counts == {"ok": 0, "failed": 0, "skipped_no_torch": 3}
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1
    for symbol in ARIMA_ERRORS:
        meta = get_forecast_meta(session, symbol)
        assert (meta.gru_status, meta.head_to_head_winner) == ("skipped_no_torch", None)
    assert get_backtest(session, "AAA", GRU_LENS) == []


def test_reset_marks_everything_not_run(session, stub_gru):
    stage.compute_and_store_neural_forecasts(session)
    assert stage.reset_neural_forecasts(session) == 3
    for symbol in ARIMA_ERRORS:
        meta = get_forecast_meta(session, symbol)
        assert (meta.gru_status, meta.gru_rmse_pct, meta.head_to_head_winner) == (GRU_NOT_RUN, None, None)
        assert get_backtest(session, symbol, GRU_LENS) == []
        assert _gru_row_count(session, symbol) == 0
