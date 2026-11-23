import { useRef } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pickCurrentSection, useCurrentSection } from "./useCurrentSection";

describe("pickCurrentSection", () => {
  it("is the last section whose top has passed the reading line", () => {
    expect(pickCurrentSection([0, 400, 900, 1300], 80, false)).toBe(0);
    expect(pickCurrentSection([-300, 60, 560, 960], 80, false)).toBe(1);
    expect(pickCurrentSection([-900, -500, 79, 480], 80, false)).toBe(2);
  });

  it("hands the highlight to the last section at the very bottom", () => {
    expect(pickCurrentSection([-900, -500, 200, 480], 80, true)).toBe(3);
  });

  it("is -1 with no sections", () => {
    expect(pickCurrentSection([], 80, false)).toBe(-1);
  });
});

// Fake layout: each section's top is its offset minus the container's scrollTop.
const OFFSETS = { one: 0, two: 500, three: 1000 };

function Story() {
  const containerRef = useRef(null);
  const [current, jumpTo] = useCurrentSection(containerRef, ["one", "two", "three"], { readingLineOffset: 20 });
  return (
    <div ref={containerRef} data-testid="container">
      <p data-testid="current">{current}</p>
      <button onClick={() => jumpTo("three")}>jump</button>
      {Object.keys(OFFSETS).map((id) => <section key={id} data-section={id} />)}
    </div>
  );
}

function layOut(container, scrollTop) {
  container.getBoundingClientRect = () => ({ top: 0, height: 600 });
  Object.defineProperty(container, "scrollTop", { configurable: true, value: scrollTop });
  Object.defineProperty(container, "clientHeight", { configurable: true, value: 600 });
  Object.defineProperty(container, "scrollHeight", { configurable: true, value: 2000 });
  container.querySelectorAll("[data-section]").forEach((section) => {
    section.getBoundingClientRect = () => ({ top: OFFSETS[section.dataset.section] - scrollTop });
  });
}

describe("useCurrentSection", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(cleanup);

  it("follows the reader as the container scrolls", async () => {
    render(<Story />);
    const container = screen.getByTestId("container");
    layOut(container, 0);
    expect(screen.getByTestId("current").textContent).toBe("one");

    layOut(container, 520);
    fireEvent.scroll(container);
    await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("two"));

    layOut(container, 1400);
    fireEvent.scroll(container);
    await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("three"));
  });

  it("jumps to a section, marks it current at once, and holds it while the scroll passes others", async () => {
    render(<Story />);
    const container = screen.getByTestId("container");
    layOut(container, 0);
    act(() => screen.getByText("jump").click());
    expect(screen.getByTestId("current").textContent).toBe("three");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });

    // Midway through the smooth scroll the second section passes the line.
    layOut(container, 520);
    fireEvent.scroll(container);
    await new Promise((settle) => setTimeout(settle, 50));
    expect(screen.getByTestId("current").textContent).toBe("three");
  });
});
