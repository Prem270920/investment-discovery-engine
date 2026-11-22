import { describe, expect, it } from "vitest";
import {
  areaPath, formatChange, formatDate, formatLevel, linePath, nearestIndex, percentChange, scalePoints,
} from "./benchmarkLine";

describe("scalePoints", () => {
  it("spreads points evenly left to right and puts higher closes higher up", () => {
    const { coords, low, high } = scalePoints([10, 20, 15], 100, 50, 0);
    expect(coords.map((point) => point.x)).toEqual([0, 50, 100]);
    expect(coords[0].y).toBe(50);   // the low sits on the bottom edge
    expect(coords[1].y).toBe(0);    // the high on the top edge
    expect(coords[2].y).toBe(25);
    expect([low, high]).toEqual([10, 20]);
  });

  it("leaves headroom so the line never touches the edges", () => {
    const { coords } = scalePoints([10, 20], 100, 50);
    expect(Math.min(...coords.map((point) => point.y))).toBeGreaterThan(0);
    expect(Math.max(...coords.map((point) => point.y))).toBeLessThan(50);
  });

  it("copes with a flat series without dividing by zero", () => {
    const { coords } = scalePoints([7, 7, 7], 100, 50);
    expect(coords.every((point) => Number.isFinite(point.y))).toBe(true);
  });
});

describe("paths", () => {
  const coords = [{ x: 0, y: 10 }, { x: 50, y: 5 }];

  it("builds a line through every point", () => {
    expect(linePath(coords)).toBe("M0.00 10.00 L50.00 5.00");
  });

  it("closes the area down to the baseline", () => {
    expect(areaPath(coords, 40)).toBe("M0.00 10.00 L50.00 5.00 L50.00 40 L0.00 40 Z");
    expect(areaPath([], 40)).toBe("");
  });
});

describe("nearestIndex", () => {
  it("maps a position across the chart to the closest day", () => {
    expect(nearestIndex(0, 11)).toBe(0);
    expect(nearestIndex(0.5, 11)).toBe(5);
    expect(nearestIndex(0.54, 11)).toBe(5);
    expect(nearestIndex(0.56, 11)).toBe(6);
    expect(nearestIndex(1, 11)).toBe(10);
  });

  it("clamps positions past either edge", () => {
    expect(nearestIndex(-0.3, 11)).toBe(0);
    expect(nearestIndex(1.4, 11)).toBe(10);
  });

  it("has nothing to point at in an empty series", () => {
    expect(nearestIndex(0.5, 0)).toBe(-1);
  });
});

describe("formatting", () => {
  it("formats an index level with thousands separators and one decimal", () => {
    expect(formatLevel(6812.4567)).toBe("6,812.5");
  });

  it("formats a stored calendar date without shifting it by time zone", () => {
    expect(formatDate("2026-11-20")).toBe("20 Nov 2026");
    expect(formatDate("2026-01-01")).toBe("1 Jan 2026");
  });

  it("signs a change with a plus or a true minus sign", () => {
    expect(formatChange(12.345)).toBe("+12.3%");
    expect(formatChange(-4.06)).toBe("−4.1%");
    expect(formatChange(0)).toBe("0.0%");
  });

  it("measures change from the first close", () => {
    expect(percentChange(200, 250)).toBe(25);
    expect(percentChange(200, 150)).toBe(-25);
  });
});
