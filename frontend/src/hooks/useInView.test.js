import { createElement } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useInView } from "./useInView";

/**
 * Stand-in for IntersectionObserver, which jsdom doesn't provide. Tests drive
 * it by hand: scrollTo(true) plays the browser telling the hook the element
 * crossed into view, scrollTo(false) that it left.
 */
class FakeIntersectionObserver {
  static latest = null;

  constructor(onIntersect, options) {
    this.onIntersect = onIntersect;
    this.options = options;
    this.watched = [];
    this.disconnected = false;
    FakeIntersectionObserver.latest = this;
  }

  observe(element) {
    this.watched.push(element);
  }

  disconnect() {
    this.disconnected = true;
    this.watched = [];
  }

  scrollTo(isIntersecting) {
    // A real observer stops calling back once disconnected, so this does too.
    if (this.disconnected) return;
    act(() => {
      this.onIntersect(this.watched.map((target) => ({ target, isIntersecting })));
    });
  }
}

function RevealProbe() {
  const [probeRef, inView] = useInView({ threshold: 0.5 });
  return createElement("div", { ref: probeRef, "data-testid": "probe", "data-inview": String(inView) });
}

const probeState = () => screen.getByTestId("probe").getAttribute("data-inview");

describe("useInView with IntersectionObserver", () => {
  beforeEach(() => {
    FakeIntersectionObserver.latest = null;
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("starts out of view and stays there until the element is reached", () => {
    render(createElement(RevealProbe));
    expect(probeState()).toBe("false");

    FakeIntersectionObserver.latest.scrollTo(false);
    expect(probeState()).toBe("false");
  });

  it("watches the probe element with the options it was given", () => {
    render(createElement(RevealProbe));
    const observer = FakeIntersectionObserver.latest;
    expect(observer.watched).toEqual([screen.getByTestId("probe")]);
    expect(observer.options).toEqual({ threshold: 0.5, rootMargin: "0px" });
  });

  it("turns true once the element scrolls into view", () => {
    render(createElement(RevealProbe));
    FakeIntersectionObserver.latest.scrollTo(true);
    expect(probeState()).toBe("true");
  });

  it("stays true after scrolling away, because it fires once", () => {
    render(createElement(RevealProbe));
    const observer = FakeIntersectionObserver.latest;
    observer.scrollTo(true);
    expect(observer.disconnected).toBe(true);

    observer.scrollTo(false);
    expect(probeState()).toBe("true");
  });

  it("stops watching when the component unmounts", () => {
    const { unmount } = render(createElement(RevealProbe));
    const observer = FakeIntersectionObserver.latest;
    unmount();
    expect(observer.disconnected).toBe(true);
  });
});

describe("useInView without IntersectionObserver", () => {
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", undefined);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("treats the element as visible from the first render", () => {
    render(createElement(RevealProbe));
    expect(probeState()).toBe("true");
  });
});
