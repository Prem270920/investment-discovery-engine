import { describe, expect, it } from "vitest";
import { layoutDots, medianTier, spreadCaption, tierNumber } from "./riskSpread";

// Builds a carousel's assets from tier numbers, 1 (Very low) to 5 (Very high).
const NAMES = ["Very low", "Low", "Moderate", "High", "Very high"];
const assetsAt = (...tiers) =>
  tiers.map((tier, position) => ({ symbol: `A${position}`, risk_tier: NAMES[tier - 1] }));

describe("tierNumber", () => {
  it("maps the five backend tier names to 1 through 5", () => {
    expect(NAMES.map(tierNumber)).toEqual([1, 2, 3, 4, 5]);
  });

  it("returns null for a missing or unknown tier", () => {
    expect(tierNumber(null)).toBeNull();
    expect(tierNumber("Extreme")).toBeNull();
  });
});

describe("spreadCaption", () => {
  // Each case is a real carousel from the current database.
  it.each([
    ["Safe & Steady", [1, 1, 1, 1, 1, 1, 1], "All calm"],
    ["Broad Market Core", [1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 4, 4, 5], "Leans calm"],
    ["Income Generators", [1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 5], "Mixes calm and volatile assets"],
    ["Market-Neutral Defensives", [3, 3, 3, 4, 4, 4, 4, 5], "Leans volatile"],
    ["Higher-Risk Growth", [3, 3, 4, 4, 5, 5, 5], "Leans volatile"],
    ["Recent Underperformers", [5, 5, 5, 5, 5], "All volatile"],
  ])("%s reads as %j", (_label, tiers, caption) => {
    expect(spreadCaption(assetsAt(...tiers))).toBe(caption);
  });

  it.each([
    [[1, 1, 1, 2], "Mostly calm"],
    [[4, 5, 5, 4], "Mostly volatile"],
    [[2, 3, 3, 3, 3], "Leans calm"],
    [[3, 3, 3], "All moderate"],
    [[3, 3, 3, 3, 3, 3, 3, 3, 3, 3], "All moderate"],
  ])("threshold case %j reads as %j", (tiers, caption) => {
    expect(spreadCaption(assetsAt(...tiers))).toBe(caption);
  });

  it("ignores assets without a tier and says so when none have one", () => {
    expect(spreadCaption([{ symbol: "X", risk_tier: null }, ...assetsAt(1, 1)])).toBe("All calm");
    expect(spreadCaption([{ symbol: "X", risk_tier: null }])).toBe("Risk not yet measured");
  });
});

describe("medianTier", () => {
  it("takes the middle tier of an odd count", () => {
    expect(medianTier(assetsAt(5, 1, 3))).toBe(3);
  });

  it("takes the lower middle tier of an even count", () => {
    expect(medianTier(assetsAt(1, 2, 4, 5))).toBe(2);
  });

  it("warms from calm to volatile across the real carousels", () => {
    const realCarousels = [
      [1, 1, 1, 1, 1, 1, 1],
      [1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 4, 4, 5],
      [1, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 5],
      [3, 3, 3, 4, 4, 4, 4, 5],
      [3, 3, 4, 4, 5, 5, 5],
      [5, 5, 5, 5, 5],
    ];
    expect(realCarousels.map((tiers) => medianTier(assetsAt(...tiers)))).toEqual([1, 2, 3, 4, 4, 5]);
  });

  it("is null when no asset has a tier", () => {
    expect(medianTier([{ symbol: "X", risk_tier: null }])).toBeNull();
  });
});

describe("layoutDots", () => {
  it("places one dot per asset with a known tier", () => {
    const { dots } = layoutDots([...assetsAt(1, 3, 5), { symbol: "X", risk_tier: null }], 4);
    expect(dots.map((dot) => [dot.symbol, dot.tier])).toEqual([["A0", 1], ["A1", 3], ["A2", 5]]);
  });

  it("stacks dots that share a tier into rows instead of overlapping", () => {
    const { dots, rows } = layoutDots(assetsAt(1, 1, 1, 1, 1, 1, 1), 4);
    expect(dots.map((dot) => [dot.column, dot.row])).toEqual([
      [0, 0], [1, 0], [2, 0], [3, 0],
      [0, 1], [1, 1], [2, 1],
    ]);
    expect(rows).toBe(2);
    const positions = new Set(dots.map((dot) => `${dot.tier}:${dot.column}:${dot.row}`));
    expect(positions.size).toBe(dots.length);
  });

  it("fills each tier independently", () => {
    const { dots, rows } = layoutDots(assetsAt(2, 4, 2), 4);
    expect(dots.map((dot) => [dot.tier, dot.column, dot.row])).toEqual([[2, 0, 0], [4, 0, 0], [2, 1, 0]]);
    expect(rows).toBe(1);
  });
});
