import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import RiskSpreadStrip from "./RiskSpreadStrip";

const ASSETS = [
  { symbol: "VGB.AX", risk_tier: "Very low" },
  { symbol: "IAF.AX", risk_tier: "Very low" },
  { symbol: "AAPL", risk_tier: "Very high" },
  { symbol: "VTI", risk_tier: "Low" },
];

const dots = () => screen.getAllByRole("button");
const dotFor = (symbol) => dots().find((dot) => dot.dataset.symbol === symbol);
const plot = () => screen.getByTestId("spread-plot");

function renderStrip(overrides = {}) {
  const props = {
    assets: ASSETS,
    highlightedSymbol: null,
    onHighlight: vi.fn(),
    onSelectAsset: vi.fn(),
    ...overrides,
  };
  render(<RiskSpreadStrip {...props} />);
  return props;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RiskSpreadStrip", () => {
  it("draws one dot per asset, labelled with its symbol and risk", () => {
    renderStrip();
    expect(dots()).toHaveLength(4);
    expect(dotFor("AAPL").getAttribute("aria-label")).toBe("AAPL: volatile, very high risk. Open details.");
  });

  it("writes a caption from the data (three of four calm reads as mostly calm)", () => {
    renderStrip();
    expect(screen.getByText("Mostly calm")).toBeTruthy();
    expect(screen.getByRole("group").getAttribute("aria-label")).toBe("Risk spread: Mostly calm");
  });

  it("places dots on their tier and stacks dots that share one side by side", () => {
    renderStrip();
    const left = (symbol) => parseFloat(dotFor(symbol).style.left);
    expect(left("IAF.AX")).toBeGreaterThan(left("VGB.AX"));
    expect(left("VTI")).toBeGreaterThan(left("IAF.AX"));
    expect(left("AAPL")).toBeGreaterThan(left("VTI"));
    expect(dotFor("AAPL").style.getPropertyValue("--dot-color")).toBe("var(--risk-temp-5)");
  });

  it("keeps every dot out of the tab order, since each card is already a tab stop", () => {
    renderStrip();
    expect(dots().every((dot) => dot.tabIndex === -1)).toBe(true);
  });

  it("reports hover and focus so the matching card can light up", () => {
    const props = renderStrip();
    fireEvent.mouseEnter(dotFor("VTI"));
    expect(props.onHighlight).toHaveBeenLastCalledWith("VTI");
    fireEvent.mouseLeave(dotFor("VTI"));
    expect(props.onHighlight).toHaveBeenLastCalledWith(null);
    fireEvent.focus(dotFor("AAPL"));
    expect(props.onHighlight).toHaveBeenLastCalledWith("AAPL");
    fireEvent.blur(dotFor("AAPL"));
    expect(props.onHighlight).toHaveBeenLastCalledWith(null);
  });

  it("opens the asset when a dot is clicked", () => {
    const props = renderStrip();
    fireEvent.click(dotFor("VGB.AX"));
    expect(props.onSelectAsset).toHaveBeenCalledWith("VGB.AX");
  });

  it("lights up only the dot whose card is highlighted", () => {
    renderStrip({ highlightedSymbol: "IAF.AX" });
    expect(dotFor("IAF.AX").className).toMatch(/highlighted/);
    expect(dotFor("VGB.AX").className).not.toMatch(/highlighted/);
  });
});

describe("RiskSpreadStrip reveal", () => {
  class HeldObserver {
    static latest = null;
    constructor(callback) { this.callback = callback; HeldObserver.latest = this; }
    observe() {}
    disconnect() {}
  }

  it("waits off screen, then reveals once the strip scrolls into view", () => {
    vi.stubGlobal("IntersectionObserver", HeldObserver);
    vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
    renderStrip();
    expect(plot().className).not.toMatch(/revealed/);
    act(() => HeldObserver.latest.callback([{ isIntersecting: true }]));
    expect(plot().className).toMatch(/revealed/);
  });

  it("shows the final state straight away under reduced motion", () => {
    vi.stubGlobal("IntersectionObserver", HeldObserver);
    vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    renderStrip();
    expect(plot().className).toMatch(/revealed/);
  });
});
