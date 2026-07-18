"""
Train and persist the clustering model

This is run intentionally, NOT on every pipeline run. 
It fits the StandardScaler and KMeans on current data, derives the
human labels from the resulting centroids, and saves all three (scaler, model,
labels) as a single versioned artifact.

The artifact bundles:
  * scaler  — the fitted StandardScaler (frozen mean/variance)
  * model   — the fitted KMeans (frozen centroids)
  * labels  — cluster_id -> human label, FROZEN at train time
"""

import logging
from datetime import datetime, timezone

import joblib
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select

from src.storage.database import SessionLocal
from src.storage.models import Asset, AssetMetric
from src.ml.model_store import MODEL_PATH, FEATURES, N_CLUSTERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train_clusters")

RANDOM_STATE = 42

UNDERPERFORMER_SHARPE_CEILING = 0.0
FALLBACK_LABEL = "Diversified Mix"


def _load_features() -> pd.DataFrame:
    """Load the feature matrix for all non-benchmark assets."""
    session = SessionLocal()
    try:
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
    finally:
        session.close()

    df = pd.DataFrame(rows, columns=["symbol"] + FEATURES)
    df["dividend_yield"] = df["dividend_yield"].fillna(0.0)
    return df.dropna(subset=FEATURES).reset_index(drop=True)


def _derive_labels(centroids: pd.DataFrame) -> dict[int, str]:
    """Assign labels by ranking clusters against each other"""
    labels: dict[int, str] = {}
    claimed: set[int] = set()

    def claim(cluster_id: int, label: str) -> None:
        if cluster_id not in claimed:
            labels[cluster_id] = label
            claimed.add(cluster_id)

    # Underperformers — genuinely negative Sharpe.
    worst = centroids["sharpe_ratio"].idxmin()
    if centroids.loc[worst, "sharpe_ratio"] < UNDERPERFORMER_SHARPE_CEILING:
        claim(worst, "Recent Underperformers")

    # Safe & Steady — lowest volatility among the rest.
    rest = centroids.drop(index=list(claimed))
    if not rest.empty:
        claim(rest["annualized_volatility"].idxmin(), "Safe & Steady")

    #Market-Neutral — beta closest to zero.
    rest = centroids.drop(index=list(claimed))
    if not rest.empty:
        claim(rest["beta"].abs().idxmin(), "Market-Neutral Defensives")

    #Higher-Risk Growth — highest BETA (not volatility; see prior fix).
    rest = centroids.drop(index=list(claimed))
    if not rest.empty:
        claim(rest["beta"].idxmax(), "Higher-Risk Growth")

    # Income Generators — highest dividend yield.
    rest = centroids.drop(index=list(claimed))
    if not rest.empty:
        claim(rest["dividend_yield"].idxmax(), "Income Generators")

    #Broad Market Core — largest remaining cluster.
    rest = centroids.drop(index=list(claimed))
    if not rest.empty:
        claim(rest["size"].idxmax(), "Broad Market Core")

    for cluster_id in centroids.index:
        if cluster_id not in labels:
            labels[cluster_id] = FALLBACK_LABEL
            logger.warning(
                "cluster %d matched no rule; fallback '%s' (vol=%.3f sharpe=%.3f "
                "beta=%.3f yield=%.2f)", cluster_id, FALLBACK_LABEL,
                centroids.loc[cluster_id, "annualized_volatility"],
                centroids.loc[cluster_id, "sharpe_ratio"],
                centroids.loc[cluster_id, "beta"],
                centroids.loc[cluster_id, "dividend_yield"],
            )
    return labels


def train() -> None:
    df = _load_features()
    if len(df) < N_CLUSTERS:
        logger.error("only %d assets — need >= %d to train", len(df), N_CLUSTERS)
        return

    X = df[FEATURES].values

    # FIT the scaler and model
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = KMeans(n_clusters=N_CLUSTERS, random_state=RANDOM_STATE, n_init=10)
    cluster_ids = model.fit_predict(X_scaled)
    df["cluster_id"] = cluster_ids

    sil = silhouette_score(X_scaled, cluster_ids)
    logger.info("trained KMeans: %d assets, %d clusters, silhouette %.4f",
                len(df), N_CLUSTERS, sil)

    # Derive labels from centroids in ORIGINAL feature units
    centroids = df.groupby("cluster_id")[FEATURES].mean()
    centroids["size"] = df.groupby("cluster_id").size()
    labels = _derive_labels(centroids)

    for cid in sorted(centroids.index):
        members = df[df["cluster_id"] == cid]["symbol"].tolist()
        logger.info("  [%s] %d: %s", labels[cid], len(members), ", ".join(members))

    # SAVE the artifact — scaler + model + frozen labels + provenance.
    artifact = {
        "scaler": scaler,
        "model": model,
        "labels": labels,
        "feature_names": FEATURES,
        "n_clusters": N_CLUSTERS,
        "silhouette": float(sil),
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(artifact, MODEL_PATH)
    logger.info("saved model artifact -> %s", MODEL_PATH)


if __name__ == "__main__":
    train()