import { describe, expect, it } from "vitest";
import { FORECAST_LINES, lensPoints } from "./forecastLines";

describe("FORECAST_LINES", () => {
  it("tells the three lines apart by style: solid, dashed, dotted", () => {
    expect(FORECAST_LINES.actual.dash).toBeUndefined();
    expect(FORECAST_LINES.arima.dash).toBe("6 4");
    expect(FORECAST_LINES.gru.dash).toMatch(/^0\.1 /);
    expect(new Set(Object.values(FORECAST_LINES).map((line) => line.label)))
      .toEqual(new Set(["Real price", "ARIMA", "GRU"]));
  });

  it("never uses a risk colour or the teal accent", () => {
    const strokes = Object.values(FORECAST_LINES).map((line) => line.stroke).join(" ");
    expect(strokes).not.toMatch(/risk|accent|teal/);
  });
});

describe("lensPoints", () => {
  it("pairs each day of the path with its band", () => {
    const lens = {
      path: [{ date: "2026-12-01", predicted: 10 }, { date: "2026-12-02", predicted: 11 }],
      band: [{ date: "2026-12-01", lower: 9, upper: 12 }, { date: "2026-12-02", lower: 8, upper: 14 }],
    };
    expect(lensPoints(lens)).toEqual([
      { date: "2026-12-01", predicted: 10, lower: 9, upper: 12 },
      { date: "2026-12-02", predicted: 11, lower: 8, upper: 14 },
    ]);
  });

  it("is empty without a lens", () => {
    expect(lensPoints(null)).toEqual([]);
  });
});
