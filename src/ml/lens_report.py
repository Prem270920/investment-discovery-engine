"""
How the two forecasting lenses compare across the universe.

Run with: python -m src.ml.lens_report

Reads the stored head to head results and prints:
  * how often each outcome happened: ARIMA wins, GRU wins, too close to call,
  * the median backtest error (RMSE as percent of price) for each lens,
  * the same medians within each cluster,
  * the five biggest margins in each direction.

Read only: it never writes to the database. The verdicts are taken as stored
by the GRU stage rather than recomputed, so this report, the API and the app
always tell the same story.
"""

from dataclasses import dataclass
from datetime import date
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.ml.compute_neural_forecasts import GRU_OK, TOO_CLOSE
from src.storage.database import SessionLocal
from src.storage.models import ARIMA_LENS, GRU_LENS, AssetMetric, ForecastMeta, Price

# How many assets each margin list shows.
TOP_MARGINS = 5

OUTCOME_NAMES = {ARIMA_LENS: "ARIMA wins", GRU_LENS: "GRU wins", TOO_CLOSE: "Too close to call"}


@dataclass(frozen=True)
class HeadToHeadResult:
    """One asset's 30 day test: both errors and the stored verdict."""
    symbol: str
    cluster_label: str
    arima_rmse_pct: float
    gru_rmse_pct: float
    verdict: str

    @property
    def margin_pct_points(self) -> float:
        return round(abs(self.arima_rmse_pct - self.gru_rmse_pct), 2)


def load_results(session: Session) -> tuple[list[HeadToHeadResult], int]:
    """Every asset where both lenses were scored, plus how many were not.

    Assets whose GRU did not finish are left out of every number, so the two
    medians always describe the same set of assets.
    """
    rows = session.execute(
        select(
            ForecastMeta.symbol, AssetMetric.cluster_label, ForecastMeta.backtest_error_pct,
            ForecastMeta.gru_rmse_pct, ForecastMeta.gru_status, ForecastMeta.head_to_head_winner,
        )
        .join(AssetMetric, AssetMetric.symbol == ForecastMeta.symbol, isouter=True)
        .order_by(ForecastMeta.symbol)
    ).all()

    compared = []
    for symbol, cluster_label, arima_error, gru_error, gru_status, verdict in rows:
        if gru_status != GRU_OK or arima_error is None or gru_error is None or verdict is None:
            continue
        compared.append(HeadToHeadResult(
            symbol=symbol, cluster_label=cluster_label or "Unclustered",
            arima_rmse_pct=arima_error, gru_rmse_pct=gru_error, verdict=verdict,
        ))
    return compared, len(rows) - len(compared)


def count_outcomes(results: list[HeadToHeadResult]) -> dict[str, int]:
    """Assets per verdict, always listing all three outcomes, zeros included."""
    counts = {verdict: 0 for verdict in OUTCOME_NAMES}
    for result in results:
        counts[result.verdict] = counts.get(result.verdict, 0) + 1
    return counts


def lens_medians(results: list[HeadToHeadResult]) -> tuple[float, float]:
    """Median ARIMA error and median GRU error over the same assets."""
    return (
        median(result.arima_rmse_pct for result in results),
        median(result.gru_rmse_pct for result in results),
    )


def medians_by_cluster(results: list[HeadToHeadResult]) -> list[tuple[str, int, float, float]]:
    """(cluster label, assets, ARIMA median, GRU median), clusters in name order."""
    by_cluster: dict[str, list[HeadToHeadResult]] = {}
    for result in results:
        by_cluster.setdefault(result.cluster_label, []).append(result)
    return [
        (label, len(members), *lens_medians(members))
        for label, members in sorted(by_cluster.items())
    ]


def biggest_margins(results: list[HeadToHeadResult], winner: str, top: int = TOP_MARGINS) -> list[HeadToHeadResult]:
    """The assets the given lens won by the widest margin, widest first."""
    wins = [result for result in results if result.verdict == winner]
    return sorted(wins, key=lambda result: (-result.margin_pct_points, result.symbol))[:top]


def format_report(results: list[HeadToHeadResult], not_compared: int, prices_through: date | None) -> str:
    if not results:
        return "No assets have both an ARIMA and a GRU score yet. Run the pipeline with torch installed."

    lines = ["Second forecasting lens: GRU against ARIMA on the same 30 held out days"]
    if prices_through is not None:
        lines.append(f"Prices through {prices_through.isoformat()}")
    lines.append(f"Assets compared: {len(results)} (not compared: {not_compared})")
    lines.append("")

    lines.append("Outcomes")
    for verdict, count in count_outcomes(results).items():
        lines.append(f"  {OUTCOME_NAMES.get(verdict, verdict):<18} {count:>3}")
    lines.append("")

    arima_median, gru_median = lens_medians(results)
    lines.append("Median backtest error (RMSE, percent of price)")
    lines.append(f"  ARIMA {arima_median:>6.2f}%")
    lines.append(f"  GRU   {gru_median:>6.2f}%")
    lines.append("")

    lines.append("Median backtest error by cluster")
    lines.append(f"  {'Cluster':<27} {'Assets':>6} {'ARIMA':>8} {'GRU':>8}")
    for label, members, cluster_arima, cluster_gru in medians_by_cluster(results):
        lines.append(f"  {label:<27} {members:>6} {cluster_arima:>7.2f}% {cluster_gru:>7.2f}%")

    for winner, heading in ((GRU_LENS, "GRU"), (ARIMA_LENS, "ARIMA")):
        lines.append("")
        lines.append(f"Biggest {heading} wins (margin in percentage points)")
        widest = biggest_margins(results, winner)
        if not widest:
            lines.append("  none")
        for result in widest:
            lines.append(
                f"  {result.symbol:<8} ARIMA {result.arima_rmse_pct:>6.2f}%  GRU {result.gru_rmse_pct:>6.2f}%"
                f"  margin {result.margin_pct_points:>5.2f}"
            )
    return "\n".join(lines)


def main() -> None:
    with SessionLocal() as session:
        results, not_compared = load_results(session)
        prices_through = session.scalar(select(func.max(Price.date)))
    print(format_report(results, not_compared, prices_through))


if __name__ == "__main__":
    main()
