/**
 * Who did better on the 30 day test, in words a beginner can take at face value.
 */

// Errors are stored to two decimals and come from a single 30 day test. A gap
// under 0.05 percentage points is too small for one test to separate the two
// models, so naming a winner would claim more than the test shows.
export const TOO_CLOSE_TO_CALL_PCT_POINTS = 0.05;

export const LENS_NAMES = { arima: "ARIMA", gru: "GRU" };

/**
 * The verdict for two backtest errors (RMSE as a percent of price).
 * Returns null unless both exist. verdict is "arima", "gru" or "close".
 */
export function judgeHeadToHead(arimaErrorPct, gruErrorPct) {
  if (arimaErrorPct == null || gruErrorPct == null) return null;
  // Rounded to the stored precision first, so 1.37 against 1.32 counts as
  // exactly 0.05 apart and not 0.0499999 after floating point subtraction.
  const gapPctPoints = Math.round(Math.abs(arimaErrorPct - gruErrorPct) * 100) / 100;
  if (gapPctPoints < TOO_CLOSE_TO_CALL_PCT_POINTS) {
    return { verdict: "close", badge: "Too close to call", gapPctPoints };
  }
  const winner = gruErrorPct < arimaErrorPct ? "gru" : "arima";
  return { verdict: winner, badge: `${LENS_NAMES[winner]} wins`, gapPctPoints };
}

export const formatErrorPct = (errorPct) => `${errorPct.toFixed(2)}%`;

/** The head to head sentence shown under the replay. */
export function headToHeadSentence(arimaErrorPct, gruErrorPct, holdoutDays) {
  const judgement = judgeHeadToHead(arimaErrorPct, gruErrorPct);
  if (!judgement) return null;
  const scores =
    `Tested on the same ${holdoutDays} unseen days. ` +
    `ARIMA off by ${formatErrorPct(arimaErrorPct)}. GRU off by ${formatErrorPct(gruErrorPct)}.`;
  return judgement.verdict === "close"
    ? `${scores} Both models were about equally accurate.`
    : scores;
}
