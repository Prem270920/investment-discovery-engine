"""
Tests for the pipeline's skip flags.

Every stage is stubbed and the engine points at an in-memory database, so
these run in the fast suite without touching the network or data/.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.pipeline as pipeline

NO_GRU_RESULTS = {"ok": 0, "failed": 0, "skipped_no_torch": 0}


@pytest.fixture
def stubbed_stages(monkeypatch):
    """Replace every stage with a recorder, so a test can see which ran."""
    stages_run = []

    def recorder(stage_name, returning):
        def stage(session):
            stages_run.append(stage_name)
            return returning
        return stage

    scratch_engine = create_engine("sqlite://")
    monkeypatch.setattr(pipeline, "engine", scratch_engine)
    monkeypatch.setattr(pipeline, "SessionLocal", sessionmaker(bind=scratch_engine))
    monkeypatch.setattr(pipeline, "_ingest_assets", recorder("ingest", (2, 10, {"fetch": [], "validation": []})))
    monkeypatch.setattr(pipeline, "ingest_benchmarks", recorder("benchmarks", 5))
    monkeypatch.setattr(pipeline, "compute_and_store_metrics", recorder("metrics", 2))
    monkeypatch.setattr(pipeline, "cluster_and_store", recorder("clusters", 2))
    monkeypatch.setattr(pipeline, "compute_and_store_forecasts", recorder("arima", (2, 0)))
    monkeypatch.setattr(pipeline, "compute_and_store_neural_forecasts", recorder("gru", NO_GRU_RESULTS))
    monkeypatch.setattr(pipeline, "reset_neural_forecasts", recorder("gru_reset", 2))
    monkeypatch.setattr(pipeline, "compute_and_store_descriptions", recorder("descriptions", (2, 0)))
    yield stages_run
    scratch_engine.dispose()


def test_skip_forecasts_finishes_and_reports_the_skip(stubbed_stages, capsys):
    # This used to raise UnboundLocalError at the summary, after the commit.
    pipeline.run(skip_forecasts=True)

    assert "arima" not in stubbed_stages
    assert stubbed_stages[-1] == "descriptions"
    summary = capsys.readouterr().out
    assert "ARIMA forecasts        : skipped (--skip-forecasts)" in summary
    assert "forecasts computed" not in summary


def test_skip_forecasts_and_skip_neural_together(stubbed_stages, capsys):
    pipeline.run(skip_forecasts=True, skip_neural=True)

    # No fresh ARIMA rows were written, so the stored GRU results still hold.
    assert not {"arima", "gru", "gru_reset"} & set(stubbed_stages)
    summary = capsys.readouterr().out
    assert "GRU forecasts          : skipped (--skip-neural)" in summary


def test_full_run_still_reports_forecast_counts(stubbed_stages, capsys):
    pipeline.run()

    assert stubbed_stages == ["ingest", "benchmarks", "metrics", "clusters", "arima", "gru", "descriptions"]
    summary = capsys.readouterr().out
    assert "forecasts computed     : 2" in summary
    assert "forecasts skipped      : 0" in summary
