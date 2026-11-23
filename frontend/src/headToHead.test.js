import { describe, expect, it } from "vitest";
import { TOO_CLOSE_TO_CALL_PCT_POINTS, headToHeadSentence, judgeHeadToHead } from "./headToHead";

describe("judgeHeadToHead", () => {
  it("names the model with the lower error", () => {
    expect(judgeHeadToHead(8.19, 5.47)).toEqual({ verdict: "gru", badge: "GRU wins", gapPctPoints: 2.72 });
    expect(judgeHeadToHead(22.8, 27.72)).toEqual({ verdict: "arima", badge: "ARIMA wins", gapPctPoints: 4.92 });
  });

  it("calls anything under the threshold too close to call", () => {
    expect(TOO_CLOSE_TO_CALL_PCT_POINTS).toBe(0.05);
    expect(judgeHeadToHead(1.63, 1.62).verdict).toBe("close");
    expect(judgeHeadToHead(1.62, 1.63).badge).toBe("Too close to call");
    expect(judgeHeadToHead(8.44, 8.44).verdict).toBe("close");
    expect(judgeHeadToHead(1.36, 1.32).verdict).toBe("close");
  });

  it("names a winner at exactly the threshold, whatever floating point does to the subtraction", () => {
    // 1.37 - 1.32 is 0.050000000000000044 and 2.46 - 2.41 is 0.04999999999999982.
    expect(judgeHeadToHead(1.37, 1.32).verdict).toBe("gru");
    expect(judgeHeadToHead(2.46, 2.41).verdict).toBe("gru");
    expect(judgeHeadToHead(1.81, 1.86).verdict).toBe("arima");
  });

  it("has no verdict without both scores", () => {
    expect(judgeHeadToHead(1.5, null)).toBeNull();
    expect(judgeHeadToHead(null, 1.5)).toBeNull();
  });
});

describe("headToHeadSentence", () => {
  it("gives both errors for a clear result", () => {
    expect(headToHeadSentence(8.19, 5.47, 30))
      .toBe("Tested on the same 30 unseen days. ARIMA off by 8.19%. GRU off by 5.47%.");
  });

  it("says both were about equally accurate when too close to call", () => {
    expect(headToHeadSentence(1.63, 1.62, 30))
      .toBe("Tested on the same 30 unseen days. ARIMA off by 1.63%. GRU off by 1.62%. Both models were about equally accurate.");
  });

  it("is null without a GRU score", () => {
    expect(headToHeadSentence(1.63, null, 30)).toBeNull();
  });
});
