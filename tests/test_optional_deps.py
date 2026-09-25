"""
Tests for the torch availability check.

Most of these swap a stand-in module into sys.modules so they behave the same
whether or not torch is really installed. The one real-import test is slow
because loading torch takes a few seconds.
"""

import sys
import types

import pytest

from src.ml import optional_deps


@pytest.fixture(autouse=True)
def fresh_probe(monkeypatch):
    # Each test needs its own import attempt, not one cached by an earlier test.
    monkeypatch.delenv(optional_deps.DISABLE_TORCH_ENV, raising=False)
    optional_deps._torch_importable.cache_clear()
    yield
    optional_deps._torch_importable.cache_clear()


@pytest.fixture
def stub_torch(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", types.ModuleType("torch"))


@pytest.fixture
def missing_torch(monkeypatch):
    # A None entry in sys.modules makes any import of that name raise ImportError.
    monkeypatch.setitem(sys.modules, "torch", None)


def test_reports_available_when_torch_imports(stub_torch):
    assert optional_deps.torch_available() is True


def test_reports_unavailable_when_torch_missing(missing_torch):
    assert optional_deps.torch_available() is False


def test_env_var_forces_unavailable_even_when_importable(stub_torch, monkeypatch):
    monkeypatch.setenv(optional_deps.DISABLE_TORCH_ENV, "1")
    assert optional_deps.torch_available() is False


def test_env_var_other_values_do_not_disable(stub_torch, monkeypatch):
    monkeypatch.setenv(optional_deps.DISABLE_TORCH_ENV, "0")
    assert optional_deps.torch_available() is True


def test_env_var_is_honoured_after_result_is_cached(stub_torch, monkeypatch):
    assert optional_deps.torch_available() is True
    monkeypatch.setenv(optional_deps.DISABLE_TORCH_ENV, "1")
    assert optional_deps.torch_available() is False


def test_import_result_is_cached(stub_torch, monkeypatch):
    assert optional_deps.torch_available() is True
    # Torch vanishing after the first check should not change the answer,
    # which shows the second call never tried to import again.
    monkeypatch.setitem(sys.modules, "torch", None)
    assert optional_deps.torch_available() is True
    assert optional_deps._torch_importable.cache_info().hits == 1


@pytest.mark.slow
def test_real_torch_is_detected_when_installed():
    pytest.importorskip("torch")
    assert optional_deps.torch_available() is True
