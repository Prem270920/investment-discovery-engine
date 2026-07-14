import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select

from src.storage.database import SessionLocal
from src.storage.models import Asset, AssetMetric


FEATURES = [
    "annualized_volatility",
    "sharpe_ratio",
    "beta",
    "dividend_yield",
]

K_RANGE = range(2, 9)

def load_feature_matrix():
    """Load features for every non-benchmark asset into a DataFrame."""
    session = SessionLocal()
    try:
        rows = session.execute(
            select(
                Asset.symbol,
                Asset.short_name,
                Asset.quote_type,
                Asset.underlying_market,
                AssetMetric.annualized_volatility,
                AssetMetric.sharpe_ratio,
                AssetMetric.beta,
                Asset.dividend_yield,
            )
            .join(AssetMetric, Asset.symbol == AssetMetric.symbol)
            .where(Asset.is_benchmark == False)
        ).all()
    finally:
        session.close()


    df = pd.DataFrame(rows, columns=[
        "symbol", "short_name", "quote_type", "underlying_market",
        "annualized_volatility", "sharpe_ratio", "beta", "dividend_yield",
    ])

    missing_yield = df["dividend_yield"].isna().sum()
    df["dividend_yield"] = df["dividend_yield"].fillna(0.0)
    if missing_yield:
        print(f"note: imputed dividend_yield=0 for {missing_yield} non-paying assets")

    before = len(df)
    df = df.dropna(subset=FEATURES)
    if len(df) < before:
        print(f"note: dropped {before - len(df)} assets with missing metrics")

    return df

def show_clusters(df: pd.DataFrame, X_scaled, k: int) -> None:
    """Print cluster membership for a given k, so we can test coherence of the clusters."""
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)
    df = df.copy()
    df["cluster"] = labels

    sil = silhouette_score(X_scaled, labels)
    print(f"\n{'=' * 70}")
    print(f"  k = {k}   (silhouette {sil:.4f})")
    print(f"{'=' * 70}")

    # Sort clusters by volatility so they read low-risk -> high-risk.
    order = (
        df.groupby("cluster")["annualized_volatility"].mean().sort_values().index
    )
    for cluster_id in order:
        members = df[df["cluster"] == cluster_id]
        print(f"\n  Cluster {cluster_id}  ({len(members)} assets)")
        print(f"    centroid: vol={members['annualized_volatility'].mean():.3f}  "
              f"sharpe={members['sharpe_ratio'].mean():>6.3f}  "
              f"beta={members['beta'].mean():>6.3f}  "
              f"yield={members['dividend_yield'].mean():.2f}")
        print(f"    members: {', '.join(members['symbol'].tolist())}")

def main() -> None:
    df = load_feature_matrix()
    print(f"\nClustering {len(df)} assets on {len(FEATURES)} features: {FEATURES}\n")

    X = df[FEATURES].values

    #Scaling features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(f"{'k':>3}  {'inertia':>10}  {'silhouette':>11}")
    print("-" * 30)
    results = []
    for k in K_RANGE:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        sil = silhouette_score(X_scaled, labels)
        results.append((k, km.inertia_, sil))
        print(f"{k:>3}  {km.inertia_:>10.2f}  {sil:>11.4f}")

    # Compare k values side by side
    for k in (4, 5, 6):
        show_clusters(df, X_scaled, k)

if __name__ == "__main__":
    main()