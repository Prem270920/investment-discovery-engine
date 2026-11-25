/**
 * How the 30 day test's result reads to a beginner.
 *
 * The verdict itself ("arima", "gru" or "too_close") is decided once, in the
 * pipeline, and arrives as head_to_head.winner. This file only puts it into
 * words, so the API, the database and the card can never disagree about it.
 */

export const LENS_NAMES = { arima: "ARIMA", gru: "GRU" };

const BADGES = {
  arima: "ARIMA wins",
  gru: "GRU wins",
  too_close: "Too close to call",
};

/** The badge for a stored verdict, or null for one this page doesn't know. */
export function verdictBadge(verdict) {
  return BADGES[verdict] ?? null;
}

export const formatErrorPct = (errorPct) => `${errorPct.toFixed(2)}%`;

/** The head to head sentence shown under the replay, or null without a verdict. */
export function headToHeadSentence(headToHead) {
  if (!verdictBadge(headToHead?.winner)) return null;
  const scores =
    `Tested on the same ${headToHead.holdout_days} unseen days. ` +
    `ARIMA off by ${formatErrorPct(headToHead.arima_rmse_pct)}. GRU off by ${formatErrorPct(headToHead.gru_rmse_pct)}.`;
  return headToHead.winner === "too_close"
    ? `${scores} Both models were about equally accurate.`
    : scores;
}
