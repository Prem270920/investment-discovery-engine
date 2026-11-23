import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getAsset, getDescription, getForecast, getPrices, getRelated } from "../api";
import { tabbableInside } from "../hooks/useFocusTrap";
import KnowledgeCard, { NOT_AVAILABLE } from "./KnowledgeCard";

vi.mock("../api", () => ({
  getAsset: vi.fn(),
  getPrices: vi.fn(),
  getForecast: vi.fn(),
  getDescription: vi.fn(),
  getRelated: vi.fn(),
}));

const priceSeries = (count, start) =>
  Array.from({ length: count }, (_, day) => ({ date: `2026-${String(1 + Math.floor(day / 28)).padStart(2, "0")}-${String(1 + (day % 28)).padStart(2, "0")}`, close: start + day * 0.1 }));

const ASSETS = {
  BND: {
    symbol: "BND", short_name: "Vanguard Total Bond Market ETF", quote_type: "ETF", currency: "USD",
    underlying_market: "US", listed_exchange: "NASDAQ", latest_close: 70.91, risk_tier: "Very low",
    annualized_volatility: 0.041, sharpe_ratio: -1.21, beta: 0.03, benchmark_symbol: "^GSPC",
    dividend_yield: 4.11, trailing_pe: null,
  },
  AGG: {
    symbol: "AGG", short_name: "iShares Core U.S. Aggregate Bond ETF", quote_type: "ETF", currency: "USD",
    underlying_market: "US", listed_exchange: "NYSE", latest_close: 99.5, risk_tier: "Very low",
    annualized_volatility: 0.045, sharpe_ratio: -1.18, beta: 0.04, benchmark_symbol: "^GSPC",
    dividend_yield: 3.9, trailing_pe: null,
  },
  "VGB.AX": {
    symbol: "VGB.AX", short_name: "VGOVBOND ETF UNITS [VGB]", quote_type: "ETF", currency: "AUD",
    underlying_market: "AU", listed_exchange: "ASX", latest_close: 46.28, risk_tier: "Very low",
    annualized_volatility: 0.04, sharpe_ratio: -0.55, beta: 0.08, benchmark_symbol: "^AXJO",
    dividend_yield: 3.3, trailing_pe: null,
  },
};

const FORECAST = {
  symbol: "BND", method: "price", arima_order: "(0, 1, 1)", backtest_error_pct: 1.44, horizon_days: 30,
  points: Array.from({ length: 30 }, (_, step) => ({ date: `2027-01-${String(step + 1).padStart(2, "0")}`, predicted: 71 + step * 0.01, lower: 70 - step * 0.05, upper: 72 + step * 0.05 })),
};

const DESCRIPTION = {
  symbol: "BND", method: "jargon",
  summary: "This index measures the performance of a wide spectrum of public, investment grade, taxable, fixed income securities in the United States.",
  jargon: [
    { term: "fixed income", plain: "bonds, which are loans to governments or companies that pay regular interest" },
    { term: "sampling", plain: "the fund holds a representative selection rather than every investment in the index" },
  ],
};

const RELATED = [
  { symbol: "AGG", short_name: "iShares Core U.S. Aggregate Bond ETF", risk_tier: "Very low" },
  { symbol: "TLT", short_name: "iShares 20+ Year Treasury Bond ETF", risk_tier: "Moderate" },
];

function serveAssets({ forecast = FORECAST, description = DESCRIPTION, related = RELATED } = {}) {
  getAsset.mockImplementation((symbol) => Promise.resolve(ASSETS[symbol]));
  getPrices.mockImplementation((symbol) => Promise.resolve({ symbol, points: priceSeries(250, symbol === "BND" ? 71.69 : 40) }));
  getForecast.mockImplementation((symbol) => Promise.resolve(symbol === "BND" ? forecast : null));
  getDescription.mockImplementation((symbol) => Promise.resolve(symbol === "BND" ? description : null));
  getRelated.mockImplementation((symbol) => Promise.resolve(symbol === "BND" ? related : []));
}

async function openCard(symbol = "BND", onClose = vi.fn()) {
  const view = render(<KnowledgeCard symbol={symbol} onClose={onClose} />);
  await act(async () => {});
  return { ...view, onClose, panel: screen.getByRole("dialog") };
}

const sectionNamed = (name) => screen.getByRole("region", { name });

beforeEach(() => {
  serveAssets();
  // jsdom has no layout, so element scrolling is a stub.
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.scrollTo = vi.fn();
  // With no layout every section measures at top 0, which reads as "scrolled to
  // the bottom" and would hand the index to the last section whenever a frame
  // happened to fire. The tracker's own tests cover measuring; here it stays put.
  vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 0);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe("four part story", () => {
  it("tells the story in four sections, in reading order, with a matching index", async () => {
    await openCard();
    const sections = screen.getAllByRole("region").map((region) => region.getAttribute("aria-labelledby"));
    expect(sections).toEqual(["story-about", "story-moves", "story-outlook", "story-similar"]);
    const index = screen.getByRole("navigation", { name: "Sections of this card" });
    expect(within(index).getAllByRole("button").map((button) => button.textContent))
      .toEqual(["What is it", "How it moves", "What might happen", "Similar assets"]);
    expect(within(index).getByRole("button", { name: "What is it" }).getAttribute("aria-current")).toBe("true");
  });

  it("jumps to a section from the index and marks it current", async () => {
    await openCard();
    const index = screen.getByRole("navigation", { name: "Sections of this card" });
    fireEvent.click(within(index).getByRole("button", { name: "What might happen" }));
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    expect(Element.prototype.scrollIntoView.mock.contexts[0]).toBe(sectionNamed("What might happen"));
    expect(within(index).getByRole("button", { name: "What might happen" }).getAttribute("aria-current")).toBe("true");
    expect(within(index).getByRole("button", { name: "What is it" }).getAttribute("aria-current")).toBeNull();
  });

  it("slides a narrow index sideways so the current entry stays in view", async () => {
    await openCard();
    const index = screen.getByRole("navigation", { name: "Sections of this card" });
    // A phone width bar: the nav shows 0 to 320px and the last entry sits at 300 to 400px.
    index.getBoundingClientRect = () => ({ left: 0, right: 320 });
    const similarButton = within(index).getByRole("button", { name: "Similar assets" });
    similarButton.getBoundingClientRect = () => ({ left: 300, right: 400 });
    fireEvent.click(similarButton);
    expect(index.scrollLeft).toBe(80);
    expect(Element.prototype.scrollIntoView.mock.contexts).not.toContain(similarButton);
  });

  it("keeps the close button in the sticky bar, away from the asset's chips", async () => {
    await openCard();
    const close = screen.getByRole("button", { name: "Close" });
    const about = sectionNamed("What is it");
    expect(about.contains(close)).toBe(false);
    expect(close.parentElement.hasAttribute("data-section-index")).toBe(true);
    expect(within(about).getByText("Very low risk")).toBeTruthy();
  });
});

describe("every piece of the old card is still there", () => {
  it("section 1: symbol, name, risk chip, type, summary and glossary", async () => {
    await openCard();
    const about = sectionNamed("What is it");
    for (const text of ["BND", "Vanguard Total Bond Market ETF", "Very low risk", "ETF", "What is this?", DESCRIPTION.summary]) {
      expect(within(about).getByText(text)).toBeTruthy();
    }
    fireEvent.click(within(about).getByRole("button", { name: "Explain the terms used (2)" }));
    expect(within(about).getByText("fixed income")).toBeTruthy();
    expect(within(about).getByText(DESCRIPTION.jargon[1].plain)).toBeTruthy();
    expect(within(about).getByRole("button", { name: "Hide (2)" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("section 1 falls back to the templated explainer when there is no description", async () => {
    await openCard("VGB.AX");
    const about = sectionNamed("What is it");
    expect(within(about).getByText(/VGB\.AX is a fund that holds many investments at once/)).toBeTruthy();
    expect(within(about).getByText(/moves largely independently of the ASX 200/)).toBeTruthy();
    expect(within(about).getByText(/dividend yield around 3\.3%/)).toBeTruthy();
  });

  it("section 2: the year chart and change, and all six metrics with a plain note each", async () => {
    await openCard();
    const moves = sectionNamed("How it moves");
    expect(within(moves).getByRole("img").getAttribute("aria-label")).toMatch(/over one year$/);
    expect(within(moves).getByTestId("chart-change").textContent).toMatch(/^1 year: [+−]\d+\.\d%/);
    const metrics = [
      ["Volatility (1y)", "4.1%"], ["Sharpe ratio", "-1.21"], ["Beta vs ^GSPC", "0.03"],
      ["Dividend yield", "4.11%"], ["P/E ratio", NOT_AVAILABLE], ["Latest close", "USD 70.91"],
    ];
    for (const [label, value] of metrics) {
      const term = within(moves).getByText(label);
      const values = Array.from(term.parentElement.querySelectorAll("dd")).map((dd) => dd.textContent);
      expect(values[0]).toBe(value);
      expect(values[1].length).toBeGreaterThan(20);
    }
  });

  it("section 3: the projection chart, the dashed projection note and the trust figure", async () => {
    await openCard();
    const outlook = sectionNamed("What might happen");
    expect(within(outlook).getByRole("img").getAttribute("aria-label")).toMatch(/^Projection chart/);
    expect(within(outlook).getByText("The dashed projection")).toBeTruthy();
    expect(within(outlook).getByText(/projects 30 trading days ahead/)).toBeTruthy();
    expect(within(outlook).getByText(/fitted to prices directly/)).toBeTruthy();
    expect(within(outlook).getByText("How much should you trust it?")).toBeTruthy();
    expect(within(outlook).getByText("1.44%")).toBeTruthy();
  });

  it("section 3 says so when there is no projection", async () => {
    serveAssets({ forecast: null });
    await openCard();
    expect(within(sectionNamed("What might happen")).getByText("No projection is available for this asset yet.")).toBeTruthy();
  });

  it("section 4: the related chips with their risk, and the disclaimer at the end", async () => {
    await openCard();
    const similar = sectionNamed("Similar assets");
    expect(within(similar).getByText("You might also like")).toBeTruthy();
    expect(within(similar).getByText("Similar funds, ranked by how alike they behave.")).toBeTruthy();
    expect(within(similar).getByRole("button", { name: /^TLT, / })).toBeTruthy();
    expect(within(similar).getByText("Moderate risk")).toBeTruthy();
    expect(screen.getByText("Educational information only. Not financial advice.")).toBeTruthy();
  });

  it("uses no em or en dash anywhere, glossary open", async () => {
    await openCard();
    fireEvent.click(screen.getByRole("button", { name: /Explain the terms used/ }));
    expect(screen.getByRole("dialog").textContent).not.toMatch(/[\u2013\u2014]/);
  });
});

describe("navigation and keyboard", () => {
  it("opens a related asset inside the same card and keeps focus in the panel", async () => {
    const { panel } = await openCard();
    fireEvent.click(screen.getByRole("button", { name: /^AGG, / }));
    await act(async () => {});
    expect(getAsset).toHaveBeenLastCalledWith("AGG");
    expect(screen.getByRole("heading", { name: "AGG" })).toBeTruthy();
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(document.activeElement).toBe(panel);
    expect(Element.prototype.scrollTo).toHaveBeenCalledWith({ top: 0 });
  });

  it("closes on Escape", async () => {
    const { onClose } = await openCard();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("takes focus when it opens, traps Tab at both ends, and returns focus to its opener", async () => {
    const opener = document.createElement("button");
    opener.textContent = "BND card";
    document.body.appendChild(opener);
    opener.focus();

    const { panel, unmount } = await openCard();
    expect(document.activeElement).toBe(panel);

    const stops = tabbableInside(panel);
    expect(stops[0].textContent).toBe("What is it");
    const last = stops[stops.length - 1];
    act(() => last.focus());
    fireEvent.keyDown(last, { key: "Tab" });
    expect(document.activeElement).toBe(stops[0]);
    fireEvent.keyDown(stops[0], { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);

    unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
