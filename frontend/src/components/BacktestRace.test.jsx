import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BacktestRace, { REPLAY_DURATION_MS } from "./BacktestRace";

const DATES = Array.from({ length: 30 }, (_, day) => `2026-10-${String(day + 1).padStart(2, "0")}`);
// Real price rises 1 a day from 100; ARIMA guesses 2% high, GRU 1% low.
const ACTUAL = DATES.map((_, day) => 100 + day);
const BACKTEST = {
  dates: DATES,
  actual: ACTUAL,
  arima: ACTUAL.map((price) => price * 1.02),
  gru: ACTUAL.map((price) => price * 0.99),
};

let queuedFrames = [];
const runFrameAt = (time) => {
  const due = queuedFrames;
  queuedFrames = [];
  act(() => due.forEach((frame) => frame(time)));
};
const cornersOf = (lineId) =>
  screen.getByTestId("backtest-chart").querySelector(`path[data-line="${lineId}"]`).getAttribute("d").match(/[ML]/g).length;
const readout = () => screen.getByTestId("gap-readout");

function preferReducedMotion(reduce) {
  window.matchMedia = vi.fn(() => ({ matches: reduce, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
}

beforeEach(() => {
  queuedFrames = [];
  preferReducedMotion(false);
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((frame) => queuedFrames.push(frame));
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => { queuedFrames = []; });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.matchMedia;
});

describe("BacktestRace", () => {
  it("shows the finished race before anything is pressed", () => {
    render(<BacktestRace backtest={BACKTEST}><p>summary</p></BacktestRace>);
    expect(cornersOf("actual")).toBe(30);
    expect(cornersOf("arima")).toBe(30);
    expect(cornersOf("gru")).toBe(30);
    expect(readout().textContent)
      .toBe("Day 30, the last test day: ARIMA 2.0% from the real price, GRU 1.0% from the real price");
    expect(screen.getByText("summary")).toBeTruthy();
  });

  it("names every line and draws them solid, dashed and dotted in neutral greys", () => {
    const { container } = render(<BacktestRace backtest={BACKTEST} />);
    expect(screen.getByRole("list", { name: "Line key" }).textContent)
      .toBe("Real priceARIMA predictionGRU prediction");
    const chart = screen.getByTestId("backtest-chart");
    expect(chart.querySelector('[data-line="actual"]').getAttribute("stroke-dasharray")).toBeNull();
    expect(chart.querySelector('[data-line="arima"]').getAttribute("stroke-dasharray")).toBe("6 4");
    expect(chart.querySelector('[data-line="gru"]').getAttribute("stroke-dasharray")).toMatch(/^0\.1 /);
    const paint = Array.from(container.querySelectorAll("[stroke], [fill]"))
      .map((node) => `${node.getAttribute("stroke")} ${node.getAttribute("fill")}`).join(" ");
    expect(paint).not.toMatch(/risk|accent/);
  });

  it("replays the days at a steady pace with a gap marker at the leading edge", () => {
    render(<BacktestRace backtest={BACKTEST} />);
    fireEvent.click(screen.getByRole("button", { name: "Replay the test" }));
    expect(cornersOf("actual")).toBe(1);

    runFrameAt(0);
    runFrameAt(REPLAY_DURATION_MS / 2);
    // Halfway is day 14.5 of 0 to 29: 15 whole days and the point reached.
    expect(cornersOf("actual")).toBe(16);
    expect(cornersOf("gru")).toBe(16);
    expect(readout().textContent).toMatch(/^Day 15 of 30: ARIMA 2\.0% from the real price, GRU 1\.0%/);
    expect(readout().getAttribute("aria-hidden")).toBe("true");

    const arimaGap = screen.getByTestId("backtest-chart").querySelector('[data-gap="arima"]');
    // The marker runs from the real price up to ARIMA's guess at the same moment.
    expect(Number(arimaGap.getAttribute("y2"))).toBeLessThan(Number(arimaGap.getAttribute("y1")));
    expect(arimaGap.getAttribute("x1")).toBe(arimaGap.getAttribute("x2"));
  });

  it("brings the result in again once the replay ends", () => {
    render(<BacktestRace backtest={BACKTEST}><p>summary</p></BacktestRace>);
    expect(screen.getByTestId("race-summary").className).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Replay the test" }));
    runFrameAt(0);
    runFrameAt(REPLAY_DURATION_MS);
    expect(screen.getByTestId("race-summary").className).toMatch(/appear/);
    expect(cornersOf("actual")).toBe(30);
    expect(readout().getAttribute("aria-hidden")).toBeNull();
  });

  it("shows the final state at once under reduced motion", () => {
    preferReducedMotion(true);
    render(<BacktestRace backtest={BACKTEST} />);
    fireEvent.click(screen.getByRole("button", { name: "Replay the test" }));
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
    expect(cornersOf("actual")).toBe(30);
    expect(cornersOf("arima")).toBe(30);
    expect(readout().textContent).toMatch(/^Day 30, the last test day/);
  });

  it("races ARIMA alone when there is no GRU", () => {
    render(<BacktestRace backtest={{ ...BACKTEST, gru: null }} />);
    expect(screen.getByTestId("backtest-chart").querySelector('[data-line="gru"]')).toBeNull();
    expect(screen.getByRole("list", { name: "Line key" }).textContent).toBe("Real priceARIMA prediction");
    expect(readout().textContent).toBe("Day 30, the last test day: ARIMA 2.0% from the real price");
    expect(screen.getByRole("img").getAttribute("aria-label")).toMatch(/with ARIMA predictions/);
  });
});
