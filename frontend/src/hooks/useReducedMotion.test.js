import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useReducedMotion } from "./useReducedMotion";

/**
 * Stand-in for window.matchMedia, which jsdom doesn't provide. setPreference
 * plays the user flipping "reduce motion" in their system settings.
 */
function installFakeMotionSetting(initiallyReduced) {
  const listeners = new Set();
  const motionQuery = {
    media: "(prefers-reduced-motion: reduce)",
    matches: initiallyReduced,
    addEventListener: (eventName, listener) => eventName === "change" && listeners.add(listener),
    removeEventListener: (eventName, listener) => eventName === "change" && listeners.delete(listener),
  };
  const matchMedia = vi.fn(() => motionQuery);
  vi.stubGlobal("matchMedia", matchMedia);

  return {
    matchMedia,
    listenerCount: () => listeners.size,
    setPreference(reduced) {
      motionQuery.matches = reduced;
      act(() => listeners.forEach((listener) => listener({ matches: reduced })));
    },
  };
}

describe("useReducedMotion", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("is false when the user has not asked for reduced motion", () => {
    const motionSetting = installFakeMotionSetting(false);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
    expect(motionSetting.matchMedia).toHaveBeenCalledWith("(prefers-reduced-motion: reduce)");
  });

  it("is true from the first render when reduced motion is already on", () => {
    installFakeMotionSetting(true);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(true);
  });

  it("follows the setting live: off, switched on, switched back off", () => {
    const motionSetting = installFakeMotionSetting(false);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);

    motionSetting.setPreference(true);
    expect(result.current).toBe(true);

    motionSetting.setPreference(false);
    expect(result.current).toBe(false);
  });

  it("stops listening when the component unmounts", () => {
    const motionSetting = installFakeMotionSetting(false);
    const { unmount } = renderHook(() => useReducedMotion());
    expect(motionSetting.listenerCount()).toBe(1);
    unmount();
    expect(motionSetting.listenerCount()).toBe(0);
  });

  it("assumes motion is fine when matchMedia is missing", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
  });
});
