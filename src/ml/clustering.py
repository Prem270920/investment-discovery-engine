"""
Clustering Inference — assign assets to the pre-trained model's clusters

This no longer fits anything. It LOADS the model trained by train_clusters.py
and uses scaler.transform() + model.predict() to assign each asset to an
existing cluster. Same model + similar data to stable, reproducible carousels.

Risk tiers (quintile buckets of volatility) are computed here, not from the model
"""

import logging

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ml.model_store import FEATURES, load_model
from src.storage.models import Asset, AssetMetric

logger = logging.getLogger("clustering")

RISK_TIER_LABELS = ["Very low", "Low", "Moderate", "High", "Very high"]


def _load_features(session: Session) -> pd.DataFrame:
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
    n_missing = int(df["dividend_yield"].isna().sum())
    df["dividend_yield"] = df["dividend_yield"].fillna(0.0)
    if n_missing:
        logger.info("imputed dividend_yield=0 for %d non-paying assets", n_missing)

    incomplete = df[df[FEATURES].isna().any(axis=1)]
    if not incomplete.empty:
        logger.warning(
            "excluded %d asset(s) from clustering — missing metrics: %s",
            len(incomplete), ", ".join(incomplete["symbol"].tolist()),
        )
    return df.dropna(subset=FEATURES).reset_index(drop=True)


def _assign_risk_tiers(df: pd.DataFrame) -> pd.Series:
    """Quintile risk tiers by volatility — relative to the current universe."""
    try:
        return pd.qcut(
            df["annualized_volatility"], q=len(RISK_TIER_LABELS),
            labels=RISK_TIER_LABELS, duplicates="drop",
        ).astype(str)
    except ValueError:
        logger.warning("could not compute quantile risk tiers (too few values)")
        return pd.Series(["Unknown"] * len(df), index=df.index)


def cluster_and_store(session: Session) -> int:
    """Assign every asset to the PRE-TRAINED model's clusters and persist."""
    df = _load_features(session)
    if df.empty:
        logger.error("no assets with complete metrics; skipping clustering")
        return 0

    artifact = load_model()
    scaler = artifact["scaler"]
    model = artifact["model"]
    labels = artifact["labels"]

    logger.info(
        "loaded model trained %s (silhouette %.4f)",
        artifact.get("trained_at", "?"), artifact.get("silhouette", float("nan")),
    )

    # INFERENCE: transform (not fit_transform), predict (not fit_predict)
    X_scaled = scaler.transform(df[FEATURES].values)
    df["cluster_id"] = model.predict(X_scaled)

    # Risk tiers — computed fresh each run
    df["risk_tier"] = _assign_risk_tiers(df)

    tier_summary = (
        df.groupby("risk_tier", observed=True)["annualized_volatility"]
        .agg(["count", "min", "max"]).reindex(RISK_TIER_LABELS).dropna()
    )
    for tier, stats in tier_summary.iterrows():
        logger.info("  risk tier '%s': %d assets, vol %.3f-%.3f",
                    tier, int(stats["count"]), stats["min"], stats["max"])

    assigned = 0
    for row in df.itertuples():
        metric = session.get(AssetMetric, row.symbol)
        if metric is None:
            continue
        metric.cluster_id = int(row.cluster_id)
        metric.cluster_label = labels.get(int(row.cluster_id), "Unknown")
        metric.risk_tier = row.risk_tier
        assigned += 1

    for cid in sorted(df["cluster_id"].unique()):
        members = df[df["cluster_id"] == cid]["symbol"].tolist()
        logger.info("  [%s] %d: %s",
                    labels.get(int(cid), "Unknown"), len(members), ", ".join(members))

    return assigned