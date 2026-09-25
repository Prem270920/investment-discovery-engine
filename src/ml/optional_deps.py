"""
Detects optional heavy dependencies so the neural stages can skip themselves
instead of crashing the pipeline or the API.

torch lives in requirements-ml.txt, not requirements.txt, so a plain install
of the app has to keep working without it.
"""

import importlib
import logging
import os
from functools import lru_cache

logger = logging.getLogger("optional_deps")

# Setting this to 1 lets us exercise the fallback path on a machine that has
# torch installed, without uninstalling it.
DISABLE_TORCH_ENV = "DISCOVERY_DISABLE_TORCH"


@lru_cache(maxsize=1)
def _torch_importable():
    # A real import rather than find_spec: a half-broken install (missing
    # native libs) is found on disk but still fails at import time.
    try:
        importlib.import_module("torch")
    except Exception as import_error:
        logger.warning("torch unavailable, neural features will be skipped: %s", import_error)
        return False
    return True


def torch_available():
    """Return True if torch can be imported and has not been disabled."""
    # The override is read on every call, outside the cache, so flipping the
    # variable takes effect without a restart.
    if os.environ.get(DISABLE_TORCH_ENV) == "1":
        return False
    return _torch_importable()
