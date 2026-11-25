"""
Compute and store GRU forecasts for every asset, scored head to head with ARIMA.

Runs as pipeline stage 5b, straight after the ARIMA stage and inside the same
transaction. For each asset that has an ARIMA forecast summary it:
  * trains the seeded GRU and stores its 30 day path under lens "gru",
  * stores what it predicted for the 30 held out days, for the replay,
  * records gru_rmse_pct and gru_status on forecast_meta,
  * sets head_to_head_winner by comparing the GRU backtest error with ARIMA's:
    "arima", "gru", or "too_close" when the gap is too small to call.

The stage never sinks the run. If torch is unavailable every asset is marked
"skipped_no_torch". If one asset fails it is marked "failed" and the loop
moves on.

Only assets with an ARIMA summary are covered. The GRU fields live on that
row, and a head to head needs both sides.
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ml.compute_forecasts import _future_trading_dates, _load_close_series, held_out_dates
from src.ml.neural_forecast import forecast_asset_gru
from src.ml.optional_deps import DISABLE_TORCH_ENV, torch_available
from src.storage.models import ARIMA_LENS, GRU_LENS, GRU_NOT_RUN, ForecastMeta
from src.storage.repository import replace_backtest, replace_forecast, update_gru_meta

logger = logging.getLogger("compute_neural_forecasts")

GRU_OK = "ok"
GRU_FAILED = "failed"
GRU_SKIPPED_NO_TORCH = "skipped_no_torch"

# head_to_head_winner when neither model clearly did better.
TOO_CLOSE = "too_close"

# Both errors are stored to 2 decimals and come from a single 30 day test. A
# gap under 0.05 percentage points is too small for one test to separate the
# models, so naming a winner would claim more than the test shows.
TOO_CLOSE_TO_CALL_PCT_POINTS = 0.05


def pick_winner(arima_rmse_pct: float | None, gru_rmse_pct: float | None) -> str | None:
    """Lower backtest error wins. Both numbers are RMSE as percent of price on
    the same 30 day holdout, so they compare directly. A gap under
    TOO_CLOSE_TO_CALL_PCT_POINTS, exact ties included, is TOO_CLOSE rather
    than a win for either side. Returns None if either side has no score."""
    if arima_rmse_pct is None or gru_rmse_pct is None:
        return None
    # Rounded to the stored precision before and after subtracting, so 1.37
    # against 1.32 is exactly 0.05 apart rather than 0.0499999 in floating point.
    gap_pct_points = round(abs(round(arima_rmse_pct, 2) - round(gru_rmse_pct, 2)), 2)
    if gap_pct_points < TOO_CLOSE_TO_CALL_PCT_POINTS:
        return TOO_CLOSE
    return GRU_LENS if gru_rmse_pct < arima_rmse_pct else ARIMA_LENS


def _metas_with_arima(session: Session) -> list[ForecastMeta]:
    return list(session.scalars(select(ForecastMeta).order_by(ForecastMeta.symbol)).all())


def _clear_gru_path(session: Session, symbol: str) -> None:
    # A failed or skipped asset must not keep an old GRU path or replay next
    # to a status saying there isn't one.
    replace_forecast(session, symbol, [], [], [], [], lens=GRU_LENS)
    replace_backtest(session, symbol, GRU_LENS, [], [], [])


def _forecast_one(session: Session, meta: ForecastMeta) -> str:
    """Run and store the GRU for one asset. Returns the winner. Raises on failure."""
    closes = _load_close_series(session, meta.symbol)
    if closes.empty:
        raise ValueError("no price history")

    gru_forecast = forecast_asset_gru(closes)
    if gru_forecast is None:
        raise ValueError(f"history too short for the GRU ({len(closes)} bars)")

    future_dates = _future_trading_dates(closes.index[-1].date(), gru_forecast["horizon"])
    replace_forecast(
        session, meta.symbol, future_dates,
        gru_forecast["predicted"], gru_forecast["lower"], gru_forecast["upper"], lens=GRU_LENS,
    )
    replace_backtest(
        session, meta.symbol, GRU_LENS, held_out_dates(closes),
        gru_forecast["backtest_actual"], gru_forecast["backtest_predicted"],
    )
    winner = pick_winner(meta.backtest_error_pct, gru_forecast["backtest_error_pct"])
    update_gru_meta(
        session, meta.symbol, GRU_OK,
        gru_rmse_pct=gru_forecast["backtest_error_pct"], head_to_head_winner=winner,
    )
    arima_text = f"{meta.backtest_error_pct:.2f}%" if meta.backtest_error_pct is not None else "n/a"
    logger.info(
        "%s: GRU %.2f%% vs ARIMA %s -> %s",
        meta.symbol, gru_forecast["backtest_error_pct"], arima_text, winner or "no winner",
    )
    return winner


def compute_and_store_neural_forecasts(session: Session) -> dict[str, int]:
    """Run the GRU lens for every asset with an ARIMA summary.

    Returns counts per gru_status. Does not commit; the pipeline owns the
    transaction.
    """
    started = time.perf_counter()
    metas = _metas_with_arima(session)
    counts = {GRU_OK: 0, GRU_FAILED: 0, GRU_SKIPPED_NO_TORCH: 0}

    if not torch_available():
        # One warning for the whole stage, not one per asset.
        logger.warning(
            "torch unavailable (not installed, broken, or %s=1); "
            "marking %d asset(s) %s",
            DISABLE_TORCH_ENV, len(metas), GRU_SKIPPED_NO_TORCH,
        )
        for meta in metas:
            _clear_gru_path(session, meta.symbol)
            update_gru_meta(session, meta.symbol, GRU_SKIPPED_NO_TORCH)
        counts[GRU_SKIPPED_NO_TORCH] = len(metas)
    else:
        for meta in metas:
            try:
                _forecast_one(session, meta)
            except Exception as exc:  # noqa: BLE001 - one asset must not stop the rest
                logger.warning(
                    "%s: GRU failed (%s: %s); continuing",
                    meta.symbol, type(exc).__name__, exc,
                )
                _clear_gru_path(session, meta.symbol)
                update_gru_meta(session, meta.symbol, GRU_FAILED)
                counts[GRU_FAILED] += 1
            else:
                counts[GRU_OK] += 1

    logger.info(
        "GRU stage finished in %.1fs: %d ok, %d failed, %d skipped_no_torch",
        time.perf_counter() - started,
        counts[GRU_OK], counts[GRU_FAILED], counts[GRU_SKIPPED_NO_TORCH],
    )
    return counts


def reset_neural_forecasts(session: Session) -> int:
    """Mark every asset's GRU side as not run and drop its GRU path.

    For runs with --skip-neural after a fresh ARIMA stage: the ARIMA writer
    replaces all of an asset's forecast rows, GRU ones included, so keeping
    the old GRU status and winner would describe a path that no longer exists.
    """
    metas = _metas_with_arima(session)
    for meta in metas:
        _clear_gru_path(session, meta.symbol)
        update_gru_meta(session, meta.symbol, GRU_NOT_RUN)
    return len(metas)
