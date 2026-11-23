import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import RiskChip from "./RiskChip";

afterEach(cleanup);

describe("RiskChip", () => {
  it.each([
    ["Very low", "Very low risk", "var(--risk-temp-1)"],
    ["Low", "Low risk", "var(--risk-temp-2)"],
    ["Moderate", "Moderate risk", "var(--risk-temp-3)"],
    ["High", "High risk", "var(--risk-temp-4)"],
    ["Very high", "Very high risk", "var(--risk-temp-5)"],
  ])("shows %s as %j in its risk temperature colour", (tier, label, colour) => {
    render(<RiskChip riskTier={tier} />);
    expect(screen.getByText(label).style.getPropertyValue("--chip-color")).toBe(colour);
  });

  it("falls back to muted ink for an unknown tier", () => {
    render(<RiskChip riskTier={null} />);
    expect(screen.getByText("Risk unknown").style.getPropertyValue("--chip-color")).toBe("var(--ink-muted)");
  });
});
