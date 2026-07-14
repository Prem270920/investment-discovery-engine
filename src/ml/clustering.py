"""
KMeans clustering

WHAT THIS DOES: groups assets by Risk behaviour (volatility, Sharpe, beta, dividend yield)

FEATURES — deliberately EXCLUDING quote_type, underlying_market, and sector.

k=6 chosen based on study. Silhouette peaked at k=6 (0.326), but the curve was flat (0.29-0.33) 
so compared k=4/5/6 and chose k=6 because it is the ONLY k where:
  * the bond cluster stays PURE (k=4 and k=5 pollute it with XLE, XLU, PG —
    a "Safe & Stable" carousel containing an energy ETF would mislead beginners)
  * the market-neutral cluster (beta = -0.06) survives at all
"""

import logging

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.storage.models import Asset, AssetMetric

logger = logging.getLogger("clustering")

FEATURES = [
    "annualized_volatility",
    "sharpe_ratio",
    "beta",
    "dividend_yield",
]

N_CLUSTERS = 6
RANDOM_STATE = 42

#cluster size threshold for filtering out small clusters (e.g. 1-2 assets) that are not meaningful
MIN_CLUSTER_SIZE = 1

# Sharpe must be genuinely negative to earn the "underperformers" label.
UNDERPERFORMER_SHARPE_CEILING = 0.0

FALLBACK_LABEL = "Diversified Mix"

def _load_features(session: Session):
    """Load the feature matrix for all non-benchmark assets."""
    rows = session.execute(
        select(
            Asset.symbol,
            AssetMetric.annualized_volatility,
            AssetMetric.sharpe_ratio,
            AssetMetric.beta,
            Asset.dividend_yield,
        )
        .join(AssetMetric, Asset.symbol == AssetMetric.symbol)
        .where(Asset.is_benchmark == False)  # noqa: E712
    ).all()

    df = pd.DataFrame(rows, columns=["symbol"] + FEATURES)

    # dividend_yield: null means the asset pays NO dividend.
    n_missing_yield = int(df["dividend_yield"].isna().sum())
    df["dividend_yield"] = df["dividend_yield"].fillna(0.0)
    if n_missing_yield:
        logger.info("imputed dividend_yield=0 for %d non-paying assets", n_missing_yield)

    incomplete = df[df[FEATURES].isna().any(axis=1)]
    if not incomplete.empty:
        logger.warning(
            "excluded %d asset(s) from clustering — missing metrics: %s",
            len(incomplete), ", ".join(incomplete["symbol"].tolist()),
        )
    return df.dropna(subset=FEATURES).reset_index(drop=True)

def _label_clusters(centroids: pd.DataFrame) -> dict[int, str]:
    """Assign human labels by ranking clusters against each other.

    Each label is claimed by exactly one cluster. Anything unclaimed gets an honest fallback and a WARNING
    """

    labels: dict[int, str] = {}
    claimed: set[int] = set()

    def claim(cluster_id: int, label: str) -> None:
        if cluster_id not in claimed:
            labels[cluster_id] = label
            claimed.add(cluster_id)

    # UNDERPERFORMERS: genuinely negative Sharpe.
    worst_sharpe = centroids["sharpe_ratio"].idxmin()
    if centroids.loc[worst_sharpe, "sharpe_ratio"] < UNDERPERFORMER_SHARPE_CEILING:
        claim(worst_sharpe, "Recent Underperformers")

    # SAFE & STEADY — lowest volatility among the rest
    unclaimed = centroids.drop(index=list(claimed))
    if not unclaimed.empty:
        claim(unclaimed["annualized_volatility"].idxmin(), "Safe & Steady")

    # MARKET-NEUTRAL — beta closest to zero
    unclaimed = centroids.drop(index=list(claimed))
    if not unclaimed.empty:
        claim(unclaimed["beta"].abs().idxmin(), "Market-Neutral Defensives")

    # HIGHER-RISK GROWTH — highest BETA
    unclaimed = centroids.drop(index=list(claimed))
    if not unclaimed.empty:
        claim(unclaimed["beta"].idxmax(), "Higher-Risk Growth")

    # INCOME GENERATORS — highest dividend yield
    unclaimed = centroids.drop(index=list(claimed))
    if not unclaimed.empty:
        claim(unclaimed["dividend_yield"].idxmax(), "Income Generators")

    # BROAD MARKET CORE — the largest remaining cluster.
    unclaimed = centroids.drop(index=list(claimed))
    if not unclaimed.empty:
        claim(unclaimed["size"].idxmax(), "Broad Market Core")

    # Anything still unlabelled gets an honest fallback + a warning
    for cluster_id in centroids.index:
        if cluster_id not in labels:
            labels[cluster_id] = FALLBACK_LABEL
            logger.warning(
                "cluster %d matched no labelling rule; using fallback '%s' "
                "(centroid: vol=%.3f sharpe=%.3f beta=%.3f yield=%.2f) "
                "— review candidate",
                cluster_id, FALLBACK_LABEL,
                centroids.loc[cluster_id, "annualized_volatility"],
                centroids.loc[cluster_id, "sharpe_ratio"],
                centroids.loc[cluster_id, "beta"],
                centroids.loc[cluster_id, "dividend_yield"],
            )

    return labels

def cluster_and_store(session: Session):
    """Cluster all assets and persist cluster_id + cluster_label

    Returns the number of assets assigned to a cluster.
    """
    df = _load_features(session)
    if len(df) < N_CLUSTERS:
        logger.error(
            "only %d assets with complete metrics — cannot form %d clusters",
            len(df), N_CLUSTERS,
        )
        return 0

    X = df[FEATURES].values

    # scaling
    X_scaled = StandardScaler().fit_transform(X)
    km = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
    df["cluster_id"] = km.fit_predict(X_scaled)

    sil = silhouette_score(X_scaled, df["cluster_id"])
    logger.info(
        "clustered %d assets into %d groups (silhouette %.4f)",
        len(df), N_CLUSTERS, sil,
    )

    centroids = df.groupby("cluster_id")[FEATURES].mean()
    centroids["size"] = df.groupby("cluster_id").size()

    labels = _label_clusters(centroids)

    # Persist.
    assigned = 0
    for row in df.itertuples():
        metric = session.get(AssetMetric, row.symbol)
        if metric is None:
            continue
        metric.cluster_id = int(row.cluster_id)
        metric.cluster_label = labels[row.cluster_id]
        assigned += 1

    for cluster_id in sorted(centroids.index):
        members = df[df["cluster_id"] == cluster_id]["symbol"].tolist()
        size = len(members)
        visible = size >= MIN_CLUSTER_SIZE
        logger.info(
            "  [%s] %d assets%s: %s",
            labels[cluster_id],
            size,
            "" if visible else "  (BELOW MIN_CLUSTER_SIZE — hidden)",
            ", ".join(members),
        )

    return assigned


