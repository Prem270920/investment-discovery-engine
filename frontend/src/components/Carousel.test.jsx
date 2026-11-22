import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Carousel from "./Carousel";

const CAROUSEL = {
  label: "Broad Market Core",
  cluster_id: 3,
  size: 3,
  assets: [
    { symbol: "VTI", short_name: "Vanguard Total Stock Market", risk_tier: "Low", sharpe_ratio: 0.54 },
    { symbol: "AAPL", short_name: "Apple Inc.", risk_tier: "Very high", sharpe_ratio: 1.06 },
    { symbol: "VOO", short_name: "Vanguard S&P 500 ETF", risk_tier: "Low", sharpe_ratio: 0.52 },
  ],
};

const cardFor = (symbol) => screen.getByRole("button", { name: new RegExp(`^${symbol.replace(".", "\\.")}, `) });
const dotFor = (symbol) => screen.getByRole("button", { name: new RegExp(`^${symbol.replace(".", "\\.")}: `) });

afterEach(cleanup);

describe("Carousel", () => {
  it("shows a spread strip with one dot per card and no wavy pulse line", () => {
    const { container } = render(<Carousel carousel={CAROUSEL} onSelectAsset={vi.fn()} />);
    expect(screen.getAllByRole("button", { name: /Open details\.$/ })).toHaveLength(3);
    expect(screen.getAllByRole("button", { name: /View details\.$/ })).toHaveLength(3);
    // The old pulse was a bare zigzag svg under the title.
    expect(container.querySelector("header svg")).toBeNull();
  });

  it("highlights the right card while its dot is hovered or focused", () => {
    render(<Carousel carousel={CAROUSEL} onSelectAsset={vi.fn()} />);
    fireEvent.mouseEnter(dotFor("AAPL"));
    expect(cardFor("AAPL").className).toMatch(/highlighted/);
    expect(cardFor("VTI").className).not.toMatch(/highlighted/);
    fireEvent.mouseLeave(dotFor("AAPL"));
    expect(cardFor("AAPL").className).not.toMatch(/highlighted/);

    fireEvent.focus(dotFor("VOO"));
    expect(cardFor("VOO").className).toMatch(/highlighted/);
  });

  it("highlights the right dot while its card is hovered or focused", () => {
    render(<Carousel carousel={CAROUSEL} onSelectAsset={vi.fn()} />);
    fireEvent.mouseEnter(cardFor("VTI"));
    expect(dotFor("VTI").className).toMatch(/highlighted/);
    expect(dotFor("VOO").className).not.toMatch(/highlighted/);
    fireEvent.blur(cardFor("VTI"));
    fireEvent.focus(cardFor("AAPL"));
    expect(dotFor("AAPL").className).toMatch(/highlighted/);
    expect(dotFor("VTI").className).not.toMatch(/highlighted/);
  });

  it("leaves cards as the only tab stops, so keyboard users highlight dots from the cards", () => {
    render(<Carousel carousel={CAROUSEL} onSelectAsset={vi.fn()} />);
    const tabStops = screen.getAllByRole("button").filter((button) => button.tabIndex >= 0);
    expect(tabStops.map((button) => button.dataset.symbol)).toEqual(["VTI", "AAPL", "VOO"]);
    expect(tabStops.every((button) => /View details\.$/.test(button.getAttribute("aria-label")))).toBe(true);
  });

  it("opens the same asset from a dot as from its card", () => {
    const onSelectAsset = vi.fn();
    render(<Carousel carousel={CAROUSEL} onSelectAsset={onSelectAsset} />);
    fireEvent.click(dotFor("AAPL"));
    fireEvent.click(cardFor("AAPL"));
    expect(onSelectAsset.mock.calls).toEqual([["AAPL"], ["AAPL"]]);
  });

  it("tints the section with the risk temperature of its middle asset", () => {
    render(<Carousel carousel={CAROUSEL} onSelectAsset={vi.fn()} />);
    const section = screen.getByRole("region", { name: "Broad Market Core" });
    expect(section.dataset.medianTier).toBe("2");
    expect(section.style.getPropertyValue("--section-temp")).toBe("var(--risk-temp-2)");
  });
});
