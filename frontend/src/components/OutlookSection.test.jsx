import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OutlookSection from "./OutlookSection";

const HISTORY = Array.from({ length: 63 }, (_, day) => ({ date: `2026-08-${day}`, close: 100 + day * 0.1 }));
const FUTURE = Array.from({ length: 30 }, (_, day) => `2026-12-${String(day + 1).padStart(2, "0")}`);
const TEST_DAYS = Array.from({ length: 30 }, (_, day) => `2026-10-${String(day + 1).padStart(2, "0")}`);

const lens = (start, rmsePct) => ({
  path: FUTURE.map((date, day) => ({ date, predicted: start + day })),
  band: FUTURE.map((date, day) => ({ date, lower: start + day - 3, upper: start + day + 3 })),
  rmse_pct: rmsePct,
});

function apiForecast({ arimaError = 8.19, gruError = 5.47, withGru = true, withBacktest = true } = {}) {
  return {
    symbol: "PG", method: "returns", arima_order: "(1, 0, 0)", backtest_error_pct: arimaError, horizon_days: 30,
    points: lens(106, arimaError).path.map((day) => ({ ...day, lower: day.predicted - 3, upper: day.predicted + 3 })),
    lenses: { arima: lens(106, arimaError), gru: withGru ? lens(110, gruError) : null },
    head_to_head: {
      winner: withGru ? (gruError < arimaError ? "gru" : "arima") : null,
      arima_rmse_pct: arimaError, gru_rmse_pct: withGru ? gruError : null,
      margin_pct_points: withGru ? Math.abs(arimaError - gruError) : null, holdout_days: 30,
    },
    backtest: withBacktest ? {
      dates: TEST_DAYS,
      actual: TEST_DAYS.map((_, day) => 100 + day),
      arima: TEST_DAYS.map((_, day) => 102 + day),
      gru: withGru ? TEST_DAYS.map((_, day) => 99 + day) : null,
    } : null,
  };
}

const renderSection = (forecast) => render(<OutlookSection forecast={forecast} history={HISTORY} currency="USD" />);
const projectionChart = () => screen.getByRole("img", { name: /^Projection chart/ });
const drawnLenses = () => Array.from(projectionChart().querySelectorAll("[data-lens]")).map((line) => line.dataset.lens);
const toggle = () => screen.getByRole("group", { name: "Projection model" });
const choose = (label) => fireEvent.click(within(toggle()).getByRole("button", { name: label }));

beforeEach(() => {
  // No frames in these tests: the replay itself is covered by BacktestRace's.
  vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 0);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("lens toggle", () => {
  it("offers ARIMA, GRU and Both, starting on ARIMA", () => {
    renderSection(apiForecast());
    const buttons = within(toggle()).getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual(["ARIMA", "GRU", "Both"]);
    expect(buttons.map((button) => button.getAttribute("aria-pressed"))).toEqual(["true", "false", "false"]);
    expect(drawnLenses()).toEqual(["arima"]);
    expect(screen.getByText("The dashed projection")).toBeTruthy();
    expect(screen.getByText("8.19%")).toBeTruthy();
  });

  it("shows the GRU's own dotted line, band and error when chosen", () => {
    renderSection(apiForecast());
    choose("GRU");
    expect(drawnLenses()).toEqual(["gru"]);
    expect(projectionChart().querySelector('[data-lens="gru"]').getAttribute("stroke-dasharray")).toMatch(/^0\.1 /);
    expect(projectionChart().querySelector('[data-band="gru"]')).toBeTruthy();
    expect(projectionChart().querySelector('[data-band="arima"]')).toBeNull();
    expect(screen.getByText("The dotted projection")).toBeTruthy();
    expect(screen.getByText("5.47%")).toBeTruthy();
    expect(projectionChart().getAttribute("aria-label")).toMatch(/from the GRU/);
  });

  it("draws both, each with its own band, and reads out both values on hover", () => {
    renderSection(apiForecast());
    choose("Both");
    expect(drawnLenses()).toEqual(["arima", "gru"]);
    expect(projectionChart().querySelectorAll("[data-band]")).toHaveLength(2);
    expect(screen.getByText("Two projections")).toBeTruthy();
    const keyLabels = within(screen.getAllByRole("list", { name: "Line key" })[0]).getAllByRole("listitem")
      .map((entry) => entry.textContent);
    expect(keyLabels).toEqual(["Real price", "ARIMA projection", "GRU projection"]);

    const chart = projectionChart();
    chart.getBoundingClientRect = () => ({ left: 0, top: 0, width: 560, height: 170, right: 560, bottom: 170 });
    fireEvent.mouseMove(chart, { clientX: 559 });
    // The last projected day: ARIMA 106 + 29, GRU 110 + 29.
    expect(chart.textContent).toBe("ARIMA USD 135.00GRU USD 139.002026-12-30 (projected)");
  });
});

describe("head to head", () => {
  it("names a clear GRU win with both errors", () => {
    renderSection(apiForecast({ arimaError: 8.19, gruError: 5.47 }));
    const line = screen.getByTestId("head-to-head");
    expect(line.textContent).toBe("GRU wins Tested on the same 30 unseen days. ARIMA off by 8.19%. GRU off by 5.47%.");
  });

  it("names a clear ARIMA win, with the same two decimals in the trust figure", () => {
    renderSection(apiForecast({ arimaError: 22.8, gruError: 27.72 }));
    expect(screen.getByText("22.80%")).toBeTruthy();
    expect(screen.getByTestId("head-to-head").textContent)
      .toBe("ARIMA wins Tested on the same 30 unseen days. ARIMA off by 22.80%. GRU off by 27.72%.");
  });

  it("calls a gap under 0.05 points too close, even though the API names a winner", () => {
    renderSection(apiForecast({ arimaError: 1.63, gruError: 1.62 }));
    expect(screen.getByTestId("head-to-head").textContent).toBe(
      "Too close to call Tested on the same 30 unseen days. ARIMA off by 1.63%. GRU off by 1.62%. Both models were about equally accurate.",
    );
  });

  it("is on screen from the start, under the replay", () => {
    renderSection(apiForecast());
    expect(within(screen.getByTestId("race-summary")).getByTestId("head-to-head")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Replay the test" })).toBeTruthy();
  });
});

describe("without a GRU result", () => {
  it("hides the toggle and the head to head line, and replays ARIMA alone", () => {
    renderSection(apiForecast({ withGru: false }));
    expect(screen.queryByRole("group", { name: "Projection model" })).toBeNull();
    expect(screen.queryByTestId("head-to-head")).toBeNull();
    expect(drawnLenses()).toEqual(["arima"]);
    const race = screen.getByTestId("backtest-chart");
    expect(race.querySelector('[data-line="arima"]')).toBeTruthy();
    expect(race.querySelector('[data-line="gru"]')).toBeNull();
    expect(screen.getByText(/the model was trained without/)).toBeTruthy();
  });

  it("keeps the GRU out of the replay when the lens is missing, even if a replay path was sent", () => {
    const forecast = apiForecast();
    forecast.lenses.gru = null;
    renderSection(forecast);
    expect(screen.getByTestId("backtest-chart").querySelector('[data-line="gru"]')).toBeNull();
  });

  it("still works for an older response with only the ARIMA points", () => {
    const olderForecast = { ...apiForecast(), lenses: undefined, head_to_head: undefined, backtest: undefined };
    renderSection(olderForecast);
    expect(drawnLenses()).toEqual(["arima"]);
    expect(screen.queryByTestId("backtest-chart")).toBeNull();
    expect(screen.getByText("The dashed projection")).toBeTruthy();
  });
});

it("uses no risk colour and no teal on any line", () => {
  const { container } = renderSection(apiForecast());
  choose("Both");
  const paint = Array.from(container.querySelectorAll("svg [stroke], svg [fill]"))
    .map((node) => `${node.getAttribute("stroke")} ${node.getAttribute("fill")}`).join(" ");
  expect(paint).not.toMatch(/risk|accent/);
});
