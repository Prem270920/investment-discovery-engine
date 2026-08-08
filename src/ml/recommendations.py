"""
'Related assets' — sector/category match, ranked by risk similarity.

WHAT THIS DOES: given an asset, find others a user would recognise as related.
For Apple that means other technology companies; for a treasury ETF, other
government-bond ETFs.
"""

import logging

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ml.model_store import FEATURES, load_model
from src.storage.models import Asset, AssetMetric

logger = logging.getLogger("recommendations")

DEFAULT_N = 6


def _feature_vector(metric: AssetMetric, dividend_yield):
    """Assemble an asset's feature vector in the same order the scaler expects.
    dividend_yield lives on Asset, the rest on AssetMetric; null yield -> 0, matching how the model was trained.
    """
    values = {
        "annualized_volatility": metric.annualized_volatility,
        "sharpe_ratio": metric.sharpe_ratio,
        "beta": metric.beta,
        "dividend_yield": dividend_yield if dividend_yield is not None else 0.0,
    }
    return [values[f] for f in FEATURES]

def get_related(session: Session, symbol: str, n: int = DEFAULT_N):
    """Return up to n symbols related to `symbol`, best first.

    Returns symbols only; the API layer hydrates them into full records
    """
    target = session.get(Asset, symbol)
    if target is None or target.is_benchmark:
        return []

    target_metric = session.get(AssetMetric, symbol)
    if target_metric is None:
        return []

    # Load every other browsable asset with complete metrics.
    rows = session.execute(
        select(Asset, AssetMetric)
        .join(AssetMetric, Asset.symbol == AssetMetric.symbol)
        .where(
            Asset.is_benchmark == False,   # noqa: E712
            Asset.symbol != symbol,
        )
    ).all()
    if not rows:
        return []
    

    # Reuse the clustering scaler so distances live in the same geometry as the clusters
    # If the model isn't trained yet, can still do sector matching without the behavioural tiebreak.
    scaler = None
    target_scaled = None
    try:
        artifact = load_model()
        scaler = artifact["scaler"]
        target_scaled = scaler.transform([_feature_vector(target_metric, target.dividend_yield)])[0]
    except Exception as exc:
        logger.warning("scaler unavailable (%s); sector match only", type(exc).__name__)

    def behavioural_distance(metric, dividend_yield) -> float:
        """Euclidean distance in scaled feature space. Large if no scaler."""
        if scaler is None or target_scaled is None:
            return 0.0
        vec = scaler.transform([_feature_vector(metric, dividend_yield)])[0]
        return float(np.linalg.norm(vec - target_scaled))
    
    # Equities match on sector; ETFs/others match on category.
    if target.quote_type == "EQUITY":
        target_key = target.sector
        key_of = lambda a: a.sector
    else:
        target_key = target.category
        key_of = lambda a: a.category

    peers = []      # same sector/category
    others = []     # everything else, for fallback
    for asset, metric in rows:
        dist = behavioural_distance(metric, asset.dividend_yield)
        entry = (dist, asset.symbol)
        if target_key is not None and key_of(asset) == target_key:
            peers.append(entry)
        else:
            others.append(entry)

    # Peers first (sorted by behavioural similarity), then backfill from others
    # (also by similarity) only if we don't have enough peers.
    peers.sort(key=lambda e: e[0])
    others.sort(key=lambda e: e[0])

    ordered = peers + others
    return [symbol for _, symbol in ordered[:n]]
    
