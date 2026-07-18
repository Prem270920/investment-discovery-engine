"""
Shared constants and loader for the persisted clustering model

Single source of truth for the model path, feature set, and cluster count
"""

from pathlib import Path

import joblib

# The committed model artifact — see train_clusters.py. Lives under models/ at project root
MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "cluster_model.joblib"

# Features the model is trained on 
FEATURES = [
    "annualized_volatility",
    "sharpe_ratio",
    "beta",
    "dividend_yield",
]

N_CLUSTERS = 6


class ModelNotTrainedError(Exception):
    """Raised when inference is attempted but no trained model artifact exists."""


def load_model():
    """Load the persisted artifact, or fail with a clear instruction."""
    if not MODEL_PATH.exists():
        raise ModelNotTrainedError(
            f"No trained model at {MODEL_PATH}. "
            f"Run:  python -m src.ml.train_clusters"
        )
    return joblib.load(MODEL_PATH)