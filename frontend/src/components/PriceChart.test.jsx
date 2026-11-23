import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import PriceChart from "./PriceChart";

const RISING = [{ date: "2026-01-01", close: 100 }, { date: "2026-06-01", close: 110 }, { date: "2026-12-01", close: 127 }];
const FALLING = [{ date: "2026-01-01", close: 100 }, { date: "2026-12-01", close: 98.9 }];
const FORECAST = {
  points: [
    { date: "2026-12-02", predicted: 128, lower: 120, upper: 136 },
    { date: "2026-12-03", predicted: 129, lower: 118, upper: 140 },
  ],
};

afterEach(cleanup);

describe("PriceChart", () => {
  it("draws every line in neutral colours, never a risk colour", () => {
    const { container } = render(<PriceChart points={RISING} forecast={FORECAST} currency="USD" />);
    const strokes = Array.from(container.querySelectorAll("path, line, stop")).map((node) => `${node.getAttribute("stroke")} ${node.getAttribute("stop-color") ?? ""}`).join(" ");
    expect(strokes).not.toMatch(/risk/);
    expect(strokes).toMatch(/var\(--data-line\)/);
  });

  it("shows the year's change with its sign and no colour of its own", () => {
    render(<PriceChart points={RISING} currency="USD" />);
    expect(screen.getByTestId("chart-change").textContent).toBe("1 year: +27.0% (USD 100.00 → 127.00)");
    cleanup();
    render(<PriceChart points={FALLING} currency="USD" />);
    expect(screen.getByTestId("chart-change").textContent).toBe("1 year: −1.1% (USD 100.00 → 98.90)");
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Price chart, 1.1 percent down over one year");
  });

  it("leaves the change line out when asked, and takes a custom description", () => {
    render(<PriceChart points={RISING} forecast={FORECAST} currency="USD" changeLabel={null} description="Projection chart" />);
    expect(screen.queryByTestId("chart-change")).toBeNull();
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe("Projection chart");
  });

  it("reads out a projected point on hover", () => {
    render(<PriceChart points={RISING} forecast={FORECAST} currency="USD" />);
    const chart = screen.getByRole("img");
    chart.getBoundingClientRect = () => ({ left: 0, top: 0, width: 560, height: 170, right: 560, bottom: 170 });
    fireEvent.mouseMove(chart, { clientX: 559 });
    expect(chart.textContent).toBe("USD 129.002026-12-03 (projected)");
  });

  it("says so when there is too little history", () => {
    render(<PriceChart points={[{ date: "2026-01-01", close: 1 }]} currency="USD" />);
    expect(screen.getByText("No price history available.")).toBeTruthy();
  });
});
