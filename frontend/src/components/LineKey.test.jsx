import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import LineKey from "./LineKey";

afterEach(cleanup);

describe("LineKey", () => {
  it("names each line beside a sample drawn in that line's own style", () => {
    render(<LineKey lineIds={["actual", "arima", "gru"]} />);
    const entries = screen.getAllByRole("listitem");
    expect(entries.map((entry) => entry.textContent)).toEqual(["Real price", "ARIMA", "GRU"]);
    const dashes = entries.map((entry) => entry.querySelector("line").getAttribute("stroke-dasharray"));
    expect(dashes[0]).toBeNull();
    expect(dashes[1]).toBe("6 4");
    expect(dashes[2]).toMatch(/^0\.1 /);
  });

  it("takes custom labels and shows only the lines asked for", () => {
    render(<LineKey lineIds={["actual", "gru"]} labels={{ gru: "GRU prediction" }} />);
    expect(screen.getAllByRole("listitem").map((entry) => entry.textContent)).toEqual(["Real price", "GRU prediction"]);
  });
});
