"""
Tests for the environment settings in src/config.py.

Each function takes the environment as an argument, so these pass a plain
dict instead of changing the real process environment.
"""

from pathlib import Path

import pytest

from src import config


def test_defaults_work_locally_with_nothing_set():
    assert config.database_path({}) == config.PROJECT_ROOT / "data" / "investments.db"
    assert config.cors_origins({}) == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert config.log_level({}) == "INFO"


def test_database_path_from_the_environment():
    assert config.database_path({"DISCOVERY_DATABASE_PATH": "/srv/discovery/prices.db"}) == Path("/srv/discovery/prices.db")


def test_relative_database_path_is_taken_from_the_repo_root():
    chosen = config.database_path({"DISCOVERY_DATABASE_PATH": "data/copy.db"})
    assert chosen == config.PROJECT_ROOT / "data" / "copy.db"


def test_blank_database_path_falls_back_to_the_default():
    assert config.database_path({"DISCOVERY_DATABASE_PATH": "  "}) == config.DEFAULT_DATABASE_PATH


def test_cors_origins_are_split_trimmed_and_lose_trailing_slashes():
    origins = config.cors_origins({"DISCOVERY_CORS_ORIGINS": " https://discovery.example.com/ ,http://localhost:5173,, "})
    assert origins == ["https://discovery.example.com", "http://localhost:5173"]


def test_empty_cors_origins_means_none():
    # The right setting when the API serves the frontend from its own address.
    assert config.cors_origins({"DISCOVERY_CORS_ORIGINS": ""}) == []


def test_log_level_is_case_insensitive():
    assert config.log_level({"DISCOVERY_LOG_LEVEL": "debug"}) == "DEBUG"
    assert config.log_level({"DISCOVERY_LOG_LEVEL": " Warning "}) == "WARNING"


def test_unknown_log_level_stops_startup_with_the_variable_named():
    with pytest.raises(ValueError, match="DISCOVERY_LOG_LEVEL='LOUD'"):
        config.log_level({"DISCOVERY_LOG_LEVEL": "loud"})
