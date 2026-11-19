"""
Tests for the GRU forecasting lens.

The band and price rebuild helpers are plain numpy and run in the fast suite.
Anything that trains a GRU is marked slow and skips if torch isn't installed.
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ml import neural_forecast, optional_deps
from src.ml.forecasting import HORIZON_DAYS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _trending_prices(price_count=160):
    rng = np.random.default_rng(42)
    trend = np.linspace(100, 130, price_count)
    wander = rng.normal(0, 2, price_count).cumsum() * 0.3
    return pd.Series(
        np.maximum(trend + wander, 1.0),
        index=pd.date_range("2025-01-01", periods=price_count, freq="B"),
    )


@pytest.fixture
def fresh_torch_probe(monkeypatch):
    monkeypatch.delenv(optional_deps.DISABLE_TORCH_ENV, raising=False)
    optional_deps._torch_importable.cache_clear()
    yield
    optional_deps._torch_importable.cache_clear()


def test_importing_the_module_does_not_import_torch():
    # A fresh interpreter, since this test session may have loaded torch already.
    probe = subprocess.run(
        [sys.executable, "-c",
         "import sys, src.ml.neural_forecast; print('torch' in sys.modules)"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    assert probe.stdout.strip() == "False"


def test_disabled_torch_raises_instead_of_training(fresh_torch_probe, monkeypatch):
    monkeypatch.setenv(optional_deps.DISABLE_TORCH_ENV, "1")
    with pytest.raises(neural_forecast.TorchUnavailableError):
        neural_forecast.forecast_asset_gru(_trending_prices())


def test_price_rebuild_matches_arima_compounding():
    daily_returns = [0.01, -0.02, 0.005]
    expected = [100 * 1.01, 100 * 1.01 * 0.98, 100 * 1.01 * 0.98 * 1.005]
    assert np.allclose(neural_forecast._compound_returns(100.0, daily_returns), expected)


def test_band_accumulates_variance_like_arima():
    flat_prices = np.full(4, 50.0)
    lower, upper = neural_forecast._accumulated_band(flat_prices, np.full(4, 0.02))
    # Half width after n steps is 0.02 * sqrt(n) of the price.
    expected_halfwidths = 50.0 * 0.02 * np.sqrt([1, 2, 3, 4])
    assert np.allclose(upper - flat_prices, expected_halfwidths)
    assert np.allclose(flat_prices - lower, expected_halfwidths)


def test_band_z_matches_arima_confidence_level():
    assert neural_forecast.BAND_Z == pytest.approx(1.959964, abs=1e-6)


def test_too_short_history_returns_none(fresh_torch_probe):
    pytest.importorskip("torch")
    assert neural_forecast.forecast_asset_gru(_trending_prices(40)) is None


@pytest.fixture(scope="module")
def gru_forecast():
    pytest.importorskip("torch")
    return neural_forecast.forecast_asset_gru(_trending_prices())


@pytest.mark.slow
def test_same_seed_gives_identical_rmse():
    pytest.importorskip("torch")
    first_run = neural_forecast.backtest_rmse_pct(_trending_prices())
    second_run = neural_forecast.backtest_rmse_pct(_trending_prices())
    assert first_run is not None
    assert first_run == second_run


@pytest.mark.slow
def test_forecast_length_is_horizon(gru_forecast):
    assert HORIZON_DAYS == 30
    assert len(gru_forecast["predicted"]) == 30
    assert len(gru_forecast["lower"]) == 30
    assert len(gru_forecast["upper"]) == 30


@pytest.mark.slow
def test_band_widens_with_horizon(gru_forecast):
    first_width = gru_forecast["upper"][0] - gru_forecast["lower"][0]
    last_width = gru_forecast["upper"][-1] - gru_forecast["lower"][-1]
    assert first_width > 0
    assert last_width > first_width


@pytest.mark.slow
def test_prediction_sits_inside_its_band(gru_forecast):
    for low, mid, high in zip(gru_forecast["lower"], gru_forecast["predicted"], gru_forecast["upper"]):
        assert low < mid < high
