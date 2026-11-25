"""
Tests for the lens comparison report.

Each test builds a small in-memory database from the real models, so the
production database is never read.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.ml import lens_report
from src.storage.database import Base
from src.storage.models import Asset, AssetMetric, Price
from src.storage.repository import update_gru_meta, upsert_arima_meta

# symbol: (cluster, ARIMA error, GRU error, GRU status, stored verdict)
STORED_RESULTS = {
    "CALM1": ("Safe & Steady", 1.40, 1.20, "ok", "gru"),
    "CALM2": ("Safe & Steady", 1.00, 1.02, "ok", "too_close"),
    "WILD1": ("Higher-Risk Growth", 10.00, 14.00, "ok", "arima"),
    "WILD2": ("Higher-Risk Growth", 6.00, 7.00, "ok", "arima"),
    "WILD3": ("Higher-Risk Growth", 8.00, 5.00, "ok", "gru"),
    "SKIP": ("Safe & Steady", 2.00, None, "skipped_no_torch", None),
}


@pytest.fixture
def session():
    scratch_engine = create_engine("sqlite://")
    Base.metadata.create_all(scratch_engine)
    scratch_session = sessionmaker(bind=scratch_engine)()
    for symbol, (cluster, arima_error, gru_error, gru_status, verdict) in STORED_RESULTS.items():
        scratch_session.add(Asset(
            symbol=symbol, short_name=symbol, quote_type="ETF", currency="USD",
            listed_exchange="NYSE", underlying_market="US", latest_close=100.0,
        ))
        scratch_session.flush()
        scratch_session.add(AssetMetric(symbol=symbol, cluster_label=cluster))
        scratch_session.add(Price(symbol=symbol, date=date(2026, 11, 20), open=1, high=1, low=1, close=1, volume=0))
        upsert_arima_meta(scratch_session, symbol, "returns", "(1, 0, 0)", arima_error, 30)
        update_gru_meta(scratch_session, symbol, gru_status, gru_rmse_pct=gru_error, head_to_head_winner=verdict)
    scratch_session.flush()
    yield scratch_session
    scratch_session.close()
    scratch_engine.dispose()


def test_only_assets_with_both_scores_are_compared(session):
    results, not_compared = lens_report.load_results(session)
    assert [result.symbol for result in results] == ["CALM1", "CALM2", "WILD1", "WILD2", "WILD3"]
    assert not_compared == 1


def test_counts_all_three_outcomes_from_the_stored_verdicts(session):
    results, _ = lens_report.load_results(session)
    assert lens_report.count_outcomes(results) == {"arima": 2, "gru": 2, "too_close": 1}


def test_counts_keep_an_outcome_that_never_happened():
    assert lens_report.count_outcomes([]) == {"arima": 0, "gru": 0, "too_close": 0}


def test_medians_cover_the_same_assets_for_both_lenses(session):
    results, _ = lens_report.load_results(session)
    # ARIMA errors 1.0, 1.4, 6, 8, 10 and GRU errors 1.02, 1.2, 5, 7, 14.
    assert lens_report.lens_medians(results) == (6.0, 5.0)


def test_medians_by_cluster(session):
    results, _ = lens_report.load_results(session)
    assert lens_report.medians_by_cluster(results) == [
        ("Higher-Risk Growth", 3, 8.0, 7.0),
        # The median of 1.02 and 1.2 is 1.11, give or take floating point.
        ("Safe & Steady", 2, 1.2, pytest.approx(1.11)),
    ]


def test_biggest_margins_each_way_skip_too_close(session):
    results, _ = lens_report.load_results(session)
    assert [(result.symbol, result.margin_pct_points) for result in lens_report.biggest_margins(results, "gru")] == [
        ("WILD3", 3.0), ("CALM1", 0.2),
    ]
    assert [result.symbol for result in lens_report.biggest_margins(results, "arima")] == ["WILD1", "WILD2"]
    assert [result.symbol for result in lens_report.biggest_margins(results, "arima", top=1)] == ["WILD1"]


def test_report_text_carries_every_section(session):
    results, not_compared = lens_report.load_results(session)
    report = lens_report.format_report(results, not_compared, date(2026, 11, 20))

    assert "Prices through 2026-11-20" in report
    assert "Assets compared: 5 (not compared: 1)" in report
    assert "  ARIMA wins           2" in report
    assert "  GRU wins             2" in report
    assert "  Too close to call    1" in report
    assert "  ARIMA   6.00%" in report
    assert "  GRU     5.00%" in report
    assert "  Higher-Risk Growth               3    8.00%    7.00%" in report
    assert "  WILD3    ARIMA   8.00%  GRU   5.00%  margin  3.00" in report


def test_report_says_so_when_nothing_was_compared():
    assert "No assets have both" in lens_report.format_report([], 3, None)


def test_main_reads_without_writing(session, monkeypatch, capsys):
    monkeypatch.setattr(lens_report, "SessionLocal", lambda: session)
    session.commit()
    lens_report.main()
    assert "Outcomes" in capsys.readouterr().out
    assert not session.dirty and not session.new
