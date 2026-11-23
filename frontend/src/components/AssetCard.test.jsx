import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import AssetCard, { SHARPE_EXPLAINER } from "./AssetCard";

const RISING = Array.from({ length: 30 }, (_, step) => 100 + step);
const FALLING = [...RISING].reverse();

const ASSET = {
  symbol: "IVV",
  short_name: "iShares Core S&P 500 ETF",
  risk_tier: "Low",
  sharpe_ratio: 0.51,
  sparkline_closes: RISING,
};

function renderCard(overrides = {}, props = {}) {
  const onSelect = vi.fn();
  const onHighlight = vi.fn();
  render(<AssetCard asset={{ ...ASSET, ...overrides }} onSelect={onSelect} onHighlight={onHighlight} {...props} />);
  return { onSelect, onHighlight, card: screen.getByRole("button") };
}

afterEach(cleanup);

describe("risk chip", () => {
  it("shows the plain label in the tier's risk temperature colour, with no separate dot", () => {
    const { card } = renderCard({ risk_tier: "Very high" });
    const chip = screen.getByText("Very high risk");
    expect(chip.style.getPropertyValue("--chip-color")).toBe("var(--risk-temp-5)");
    expect(card.querySelector("[class*='dot']")).toBeNull();
  });

  it("falls back to muted ink when the tier is unknown", () => {
    renderCard({ risk_tier: null });
    expect(screen.getByText("Risk unknown").style.getPropertyValue("--chip-color")).toBe("var(--ink-muted)");
  });
});

describe("sparkline", () => {
  it("draws one path through the closes, held undrawn by a unit stroke dash", () => {
    renderCard();
    const path = screen.getByTestId("card-sparkline").querySelector("path");
    expect(path.getAttribute("pathLength")).toBe("1");
    expect(path.getAttribute("d").match(/[ML]/g)).toHaveLength(30);
  });

  it("draws every line in the one neutral data colour, whichever way it went", () => {
    const lineColour = () => screen.getByTestId("card-sparkline").querySelector("path").style.getPropertyValue("--spark-color");
    renderCard();
    expect(lineColour()).toBe("");
    cleanup();
    renderCard({ sparkline_closes: FALLING });
    expect(lineColour()).toBe("");
  });

  it("shows the change over the window as a signed number at rest, with no colour of its own", () => {
    renderCard();
    // 100 to 129 is a 29% rise.
    expect(screen.getByTestId("card-change").textContent).toBe("+29.0% in 90 trading days");
    expect(screen.getByTestId("card-change").style.color).toBe("");
    cleanup();
    renderCard({ sparkline_closes: FALLING });
    expect(screen.getByTestId("card-change").textContent).toBe("\u221222.5% in 90 trading days");
  });

  it("says so plainly when there are no recent prices", () => {
    renderCard({ sparkline_closes: null });
    expect(screen.getByTestId("card-change").textContent).toBe("No recent prices");
  });

  it("keeps its space but draws nothing without at least two closes", () => {
    renderCard({ sparkline_closes: null });
    expect(screen.getByTestId("card-sparkline").querySelector("path")).toBeNull();
    cleanup();
    renderCard({ sparkline_closes: [5] });
    expect(screen.getByTestId("card-sparkline").querySelector("path")).toBeNull();
  });
});

describe("Sharpe explainer", () => {
  it("is always available to screen readers through the card's description", () => {
    const { card } = renderCard();
    const description = document.getElementById(card.getAttribute("aria-describedby"));
    expect(description.textContent).toBe(`Sharpe ratio: ${SHARPE_EXPLAINER}`);
  });

  it("appears as a tooltip while the info mark is hovered", () => {
    renderCard();
    expect(screen.queryByRole("tooltip", { hidden: true })).toBeNull();
    fireEvent.mouseEnter(screen.getByTestId("sharpe-info"));
    expect(screen.getByRole("tooltip", { hidden: true }).textContent).toBe(SHARPE_EXPLAINER);
    fireEvent.mouseLeave(screen.getByTestId("sharpe-info"));
    expect(screen.queryByRole("tooltip", { hidden: true })).toBeNull();
  });

  it("appears when the card gets keyboard focus and goes when it loses it", () => {
    const { card } = renderCard();
    act(() => card.focus());
    expect(screen.getByRole("tooltip", { hidden: true }).textContent).toBe(SHARPE_EXPLAINER);
    act(() => card.blur());
    expect(screen.queryByRole("tooltip", { hidden: true })).toBeNull();
  });

  it("opens below the info mark, and when it must flip up it clears the whole card", () => {
    const { card } = renderCard();
    const info = screen.getByTestId("sharpe-info");
    card.getBoundingClientRect = () => ({ top: 200, bottom: 400, left: 50, right: 250, width: 200, height: 200 });
    const placeAt = (top) => {
      info.getBoundingClientRect = () => ({ top, bottom: top + 14, left: 100, right: 114, width: 14, height: 14 });
      fireEvent.mouseEnter(info);
      const tip = screen.getByRole("tooltip", { hidden: true });
      const placement = [tip.dataset.placement, parseFloat(tip.style.top)];
      fireEvent.mouseLeave(info);
      return placement;
    };
    expect(placeAt(370)).toEqual(["below", 392]);
    // No room below: it sits above the card's top edge, not just above the mark.
    expect(placeAt(window.innerHeight - 30)).toEqual(["above", 192]);
  });

  it("closes when the page scrolls, since its anchor has moved", () => {
    renderCard();
    fireEvent.mouseEnter(screen.getByTestId("sharpe-info"));
    fireEvent.scroll(window);
    expect(screen.queryByRole("tooltip", { hidden: true })).toBeNull();
  });
});

describe("full name tooltip", () => {
  const sizeName = (scrollWidth, clientWidth) => {
    const name = screen.getByTestId("card-name");
    Object.defineProperty(name, "scrollWidth", { configurable: true, value: scrollWidth });
    Object.defineProperty(name, "clientWidth", { configurable: true, value: clientWidth });
    return name;
  };

  it("offers the full name only when it is cut short", () => {
    renderCard();
    const name = sizeName(240, 166);
    fireEvent.mouseEnter(name);
    expect(name.title).toBe("iShares Core S&P 500 ETF");
  });

  it("adds no tooltip when the whole name already fits", () => {
    renderCard({ short_name: "Apple Inc." });
    const name = sizeName(70, 166);
    fireEvent.mouseEnter(name);
    expect(name.title).toBe("");
  });

  it("puts the full name in the card's accessible name either way", () => {
    const { card } = renderCard();
    expect(card.getAttribute("aria-label")).toBe("IVV, iShares Core S&P 500 ETF, Low risk. View details.");
  });
});

describe("behaviour kept from before", () => {
  it("shows the Sharpe figure at rest and n/a when it is missing", () => {
    renderCard();
    expect(screen.getByText("0.51")).toBeTruthy();
    cleanup();
    renderCard({ sharpe_ratio: null });
    expect(screen.getByText("n/a")).toBeTruthy();
  });

  it("opens the asset on click and reports hover for the spread strip", () => {
    const { card, onSelect, onHighlight } = renderCard();
    fireEvent.click(card);
    fireEvent.mouseEnter(card);
    fireEvent.mouseLeave(card);
    expect(onSelect).toHaveBeenCalledWith("IVV");
    expect(onHighlight.mock.calls).toEqual([["IVV"], [null]]);
  });
});
