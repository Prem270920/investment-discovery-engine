import { describe, expect, it } from "vitest";
import * as headToHead from "./headToHead";

const { formatErrorPct, headToHeadSentence, verdictBadge } = headToHead;

const result = (winner, arima, gru) => ({
  winner, arima_rmse_pct: arima, gru_rmse_pct: gru, margin_pct_points: Math.abs(arima - gru), holdout_days: 30,
});

describe("verdictBadge", () => {
  it("words each verdict the pipeline can store", () => {
    expect(verdictBadge("gru")).toBe("GRU wins");
    expect(verdictBadge("arima")).toBe("ARIMA wins");
    expect(verdictBadge("too_close")).toBe("Too close to call");
  });

  it("has nothing to say for a missing or unknown verdict", () => {
    expect(verdictBadge(null)).toBeNull();
    expect(verdictBadge(undefined)).toBeNull();
    expect(verdictBadge("draw")).toBeNull();
  });

  it("no longer holds a threshold of its own", () => {
    expect(Object.keys(headToHead)).not.toContain("TOO_CLOSE_TO_CALL_PCT_POINTS");
    expect(Object.keys(headToHead)).not.toContain("judgeHeadToHead");
  });
});

describe("headToHeadSentence", () => {
  it("gives both errors for a clear result", () => {
    expect(headToHeadSentence(result("gru", 8.19, 5.47)))
      .toBe("Tested on the same 30 unseen days. ARIMA off by 8.19%. GRU off by 5.47%.");
    expect(headToHeadSentence(result("arima", 22.8, 27.72)))
      .toBe("Tested on the same 30 unseen days. ARIMA off by 22.80%. GRU off by 27.72%.");
  });

  it("says both were about equally accurate for a too close verdict", () => {
    expect(headToHeadSentence(result("too_close", 1.63, 1.62)))
      .toBe("Tested on the same 30 unseen days. ARIMA off by 1.63%. GRU off by 1.62%. Both models were about equally accurate.");
  });

  it("is null without a verdict", () => {
    expect(headToHeadSentence(null)).toBeNull();
    expect(headToHeadSentence(result(null, 1.63, 1.62))).toBeNull();
  });
});

describe("formatErrorPct", () => {
  it("always shows two decimals", () => {
    expect(formatErrorPct(22.8)).toBe("22.80%");
    expect(formatErrorPct(1.6)).toBe("1.60%");
  });
});
