"""
Settings read from environment variables, with defaults that work locally.

Nothing needs setting to run on a laptop. A deployment sets only what differs:

  DISCOVERY_DATABASE_PATH   SQLite file to read and write.
                            Default: data/investments.db in the repo.
  DISCOVERY_CORS_ORIGINS    Comma separated origins allowed to call the API
                            from another address. Default: the Vite dev server.
                            When the API serves the built frontend itself, the
                            page and the API share an address and need no entry.
  DISCOVERY_LOG_LEVEL       DEBUG, INFO, WARNING, ERROR or CRITICAL.
                            Default: INFO.

Each value is read once, at import. A bad value stops startup with a message
naming the variable, rather than letting the app run half configured.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATABASE_PATH_ENV = "DISCOVERY_DATABASE_PATH"
CORS_ORIGINS_ENV = "DISCOVERY_CORS_ORIGINS"
LOG_LEVEL_ENV = "DISCOVERY_LOG_LEVEL"

DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "investments.db"
DEFAULT_CORS_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Where `npm run build` puts the frontend; the API serves it from here.
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


def database_path(environ=os.environ) -> Path:
    raw_path = environ.get(DATABASE_PATH_ENV, "").strip()
    if not raw_path:
        return DEFAULT_DATABASE_PATH
    # Relative paths are taken from the repo root, not from wherever the
    # server happened to be started.
    chosen = Path(raw_path).expanduser()
    return chosen if chosen.is_absolute() else PROJECT_ROOT / chosen


def cors_origins(environ=os.environ) -> list[str]:
    raw_origins = environ.get(CORS_ORIGINS_ENV)
    if raw_origins is None:
        return list(DEFAULT_CORS_ORIGINS)
    # Set but empty means "no other origins": the right value when the API
    # serves the frontend from the same address.
    return [origin.strip().rstrip("/") for origin in raw_origins.split(",") if origin.strip()]


def log_level(environ=os.environ) -> str:
    chosen = environ.get(LOG_LEVEL_ENV, "").strip().upper() or DEFAULT_LOG_LEVEL
    if chosen not in LOG_LEVELS:
        raise ValueError(f"{LOG_LEVEL_ENV}={chosen!r} is not one of {', '.join(LOG_LEVELS)}")
    return chosen


DATABASE_PATH = database_path()
CORS_ORIGINS = cors_origins()
LOG_LEVEL = log_level()
