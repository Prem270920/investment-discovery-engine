import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { searchAssets } from "../api";
import RiskChip from "./RiskChip";
import SearchBar from "./SearchBar";

vi.mock("../api", () => ({ searchAssets: vi.fn() }));

const match = (symbol, shortName, riskTier) => ({ symbol, short_name: shortName, risk_tier: riskTier });

// One asset per tier, plus one the backend could not place.
const EVERY_TIER = [
  match("BND", "Vanguard Total Bond Market ETF", "Very low"),
  match("VOO", "Vanguard S&P 500 ETF", "Low"),
  match("VEA", "Vanguard FTSE Developed Markets", "Moderate"),
  match("PG", "Procter & Gamble Company (The)", "High"),
  match("NVDA", "NVIDIA Corporation", "Very high"),
  match("NEW", "Freshly listed fund", null),
];

const searchBox = () => screen.getByRole("textbox", { name: "Search assets" });
const typeQuery = (text) => fireEvent.change(searchBox(), { target: { value: text } });
// The box waits 200ms after typing stops, so results arrive a moment later.
const shownResults = async () => within(await screen.findByRole("listbox")).getAllByRole("listitem");
const symbolOf = (row) => row.querySelector("[class*='resultSymbol']").textContent;
const dotOf = (row) => row.querySelector("[class*='dot']");

beforeEach(() => {
  searchAssets.mockResolvedValue(EVERY_TIER);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SearchBar", () => {
  it("colours each result's dot exactly as RiskChip colours that tier", async () => {
    render(<SearchBar onSelectAsset={vi.fn()} />);
    typeQuery("v");
    const rows = await shownResults();
    expect(rows).toHaveLength(EVERY_TIER.length);

    for (const [position, row] of rows.entries()) {
      const { container } = render(<RiskChip riskTier={EVERY_TIER[position].risk_tier} />);
      const chipColour = container.firstChild.style.getPropertyValue("--chip-color");
      expect(dotOf(row).style.background).toBe(chipColour);
    }
    expect(rows.map((row) => dotOf(row).style.background)).toEqual([
      "var(--risk-temp-1)", "var(--risk-temp-2)", "var(--risk-temp-3)",
      "var(--risk-temp-4)", "var(--risk-temp-5)", "var(--ink-muted)",
    ]);
  });

  it("keeps an exact ticker match first, in the order the API ranked it, without re-sorting", async () => {
    // The API ranks exact ticker, then ticker prefix, then name matches. Here
    // that order is also the reverse of alphabetical, so any re-sort would show.
    searchAssets.mockResolvedValue([
      match("XLF", "State Street Financial Select Sector", "Moderate"),
      match("XLFX", "Leveraged financials", "Very high"),
      match("AXLF", "Another fund with XLF inside", "Low"),
    ]);
    render(<SearchBar onSelectAsset={vi.fn()} />);
    typeQuery("xlf");
    const rows = await shownResults();
    expect(searchAssets).toHaveBeenCalledWith("xlf");
    expect(rows.map(symbolOf)).toEqual(["XLF", "XLFX", "AXLF"]);
  });

  it("clears the results as soon as the box is emptied, and does not search for nothing", async () => {
    render(<SearchBar onSelectAsset={vi.fn()} />);
    typeQuery("v");
    await shownResults();
    expect(searchAssets).toHaveBeenCalledTimes(1);

    typeQuery("");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.queryByText(/No matches/)).toBeNull();

    // Focusing the empty box again must not bring the old list back.
    fireEvent.focus(searchBox());
    await new Promise((settle) => setTimeout(settle, 300));
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(searchAssets).toHaveBeenCalledTimes(1);
  });
});
