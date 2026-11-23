import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useReplay } from "./useReplay";

// Frames run only when a test says so, at the time it gives.
let queuedFrames = [];
const runFrameAt = (time) => {
  const due = queuedFrames;
  queuedFrames = [];
  act(() => due.forEach((frame) => frame(time)));
};

beforeEach(() => {
  queuedFrames = [];
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((frame) => queuedFrames.push(frame));
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => { queuedFrames = []; });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useReplay", () => {
  it("rests at the finished state before anything is pressed", () => {
    const { result } = renderHook(() => useReplay(3000, false));
    expect(result.current.progress).toBe(1);
    expect(result.current.playing).toBe(false);
  });

  it("rewinds and plays to the end over the duration", () => {
    const { result } = renderHook(() => useReplay(3000, false));
    act(() => result.current.start());
    expect(result.current.progress).toBe(0);
    expect(result.current.playing).toBe(true);

    runFrameAt(1000);
    runFrameAt(2500);
    expect(result.current.progress).toBe(0.5);
    runFrameAt(4000);
    expect(result.current.progress).toBe(1);
    expect(result.current.playing).toBe(false);
    expect(result.current.finishedCount).toBe(1);
    expect(queuedFrames).toHaveLength(0);
  });

  it("starts over when pressed mid replay", () => {
    const { result } = renderHook(() => useReplay(3000, false));
    act(() => result.current.start());
    runFrameAt(0);
    runFrameAt(2000);
    act(() => result.current.start());
    expect(result.current.progress).toBe(0);
    runFrameAt(5000);
    runFrameAt(5300);
    expect(result.current.progress).toBeCloseTo(0.1);
    expect(result.current.finishedCount).toBe(0);
  });

  it("jumps straight to the end under reduced motion", () => {
    const { result } = renderHook(() => useReplay(3000, true));
    act(() => result.current.start());
    expect(result.current.progress).toBe(1);
    expect(result.current.playing).toBe(false);
    expect(result.current.finishedCount).toBe(1);
    expect(window.requestAnimationFrame).not.toHaveBeenCalled();
  });

  it("stops scheduling frames once unmounted", () => {
    const { result, unmount } = renderHook(() => useReplay(3000, false));
    act(() => result.current.start());
    unmount();
    expect(window.cancelAnimationFrame).toHaveBeenCalled();
    expect(queuedFrames).toHaveLength(0);
  });
});
