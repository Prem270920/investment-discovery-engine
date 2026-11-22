import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getBenchmarkPrices } from "../api";
import BenchmarkHero from "./BenchmarkHero";

vi.mock("../api", () => ({ getBenchmarkPrices: vi.fn() }));

const GSPC = {
  symbol: "^GSPC",
  name: "S&P 500",
  points: [
    { date: "2026-11-16", close: 6000 },
    { date: "2026-11-17", close: 6100 },
    { date: "2026-11-18", close: 5900 },
    { date: "2026-11-19", close: 6300 },
  ],
};
const AXJO = {
  symbol: "^AXJO",
  name: "S&P/ASX 200",
  points: [
    { date: "2026-11-19", close: 8000 },
    { date: "2026-11-20", close: 8400 },
  ],
};

// A promise the test resolves by hand, to look at the loading state.
function heldResponse() {
  let release;
  const promise = new Promise((resolve) => { release = resolve; });
  return { promise, release };
}

const level = () => screen.getByTestId("hero-level").textContent;
const shownDate = () => screen.getByTestId("hero-date").textContent;
const chart = () => screen.getByTestId("benchmark-chart");

async function renderHero(symbol = "^GSPC") {
  const view = render(<BenchmarkHero symbol={symbol} note="Why this index matters." />);
  await act(async () => {});
  return view;
}

beforeEach(() => {
  getBenchmarkPrices.mockImplementation((symbol) => Promise.resolve(symbol === "^AXJO" ? AXJO : GSPC));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("BenchmarkHero", () => {
  it("shows the latest level, date, year change and range without any interaction", async () => {
    await renderHero();
    expect(screen.getByRole("heading", { name: "S&P 500" })).toBeTruthy();
    expect(screen.getByText("Why this index matters.")).toBeTruthy();
    expect(level()).toBe("6,300.0");
    expect(shownDate()).toBe("19 Nov 2026");
    expect(screen.getByText("+5.0%")).toBeTruthy();
    expect(screen.getByText("Year range 5,900.0 to 6,300.0")).toBeTruthy();
    expect(getBenchmarkPrices).toHaveBeenCalledWith("^GSPC", 365);
  });

  it("scrubs with the arrow keys, Home and End, and Escape returns to the latest day", async () => {
    await renderHero();
    fireEvent.keyDown(chart(), { key: "ArrowLeft" });
    expect([shownDate(), level()]).toEqual(["18 Nov 2026", "5,900.0"]);
    expect(screen.getByText("−1.7%")).toBeTruthy();
    expect(chart().getAttribute("aria-valuetext")).toBe("18 Nov 2026: 5,900.0");

    fireEvent.keyDown(chart(), { key: "Home" });
    expect(shownDate()).toBe("16 Nov 2026");
    fireEvent.keyDown(chart(), { key: "ArrowLeft" });
    expect(shownDate()).toBe("16 Nov 2026");

    fireEvent.keyDown(chart(), { key: "End" });
    expect(shownDate()).toBe("19 Nov 2026");
    fireEvent.keyDown(chart(), { key: "Escape" });
    expect(screen.getByText("over the year", { exact: false })).toBeTruthy();
  });

  it("scrubs to the day under the pointer and resets when the pointer leaves", async () => {
    await renderHero();
    chart().getBoundingClientRect = () => ({ left: 100, width: 300, top: 0, height: 180, right: 400, bottom: 180 });
    fireEvent.pointerMove(chart(), { clientX: 200 });
    expect(shownDate()).toBe("17 Nov 2026");
    fireEvent.pointerLeave(chart());
    expect(shownDate()).toBe("19 Nov 2026");
  });

  it("is a focusable slider so keyboard users can reach it", async () => {
    await renderHero();
    expect(chart().getAttribute("role")).toBe("slider");
    expect(chart().tabIndex).toBe(0);
    expect(chart().getAttribute("aria-valuenow")).toBe("3");
  });

  it("switches benchmark without ever showing the old line under the new name", async () => {
    const view = await renderHero("^GSPC");
    const pending = heldResponse();
    getBenchmarkPrices.mockImplementation(() => pending.promise);
    view.rerender(<BenchmarkHero symbol="^AXJO" note="Australian note." />);

    expect(screen.queryByRole("heading", { name: "S&P 500" })).toBeNull();
    expect(screen.getByRole("region", { name: "Loading market backdrop" })).toBeTruthy();

    await act(async () => pending.release(AXJO));
    expect(screen.getByRole("heading", { name: "S&P/ASX 200" })).toBeTruthy();
    expect(level()).toBe("8,400.0");
  });

  it("renders nothing when the benchmark can't be loaded", async () => {
    getBenchmarkPrices.mockImplementation(() => Promise.reject(new Error("offline")));
    const { container } = await renderHero();
    expect(container.innerHTML).toBe("");
  });
});
