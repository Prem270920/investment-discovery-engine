import { useEffect, useState } from "react";

const FOCUSABLE = [
  "a[href]", "button:not([disabled])", "input:not([disabled])", "select:not([disabled])",
  "textarea:not([disabled])", "[tabindex]:not([tabindex='-1'])",
].join(",");

/** Elements inside container that Tab can reach, in order. */
export function tabbableInside(container) {
  return Array.from(container.querySelectorAll(FOCUSABLE)).filter(
    (element) => !element.closest("[hidden]") && element.getAttribute("aria-hidden") !== "true",
  );
}

/**
 * Keeps keyboard focus inside a modal while it is open, and hands it back to
 * whatever had focus before (the card that opened it) when it closes.
 *
 * Tab past the last control wraps to the first and Shift+Tab before the
 * first wraps to the last. If focus ever lands outside (the control that had
 * it was removed, say), it is pulled back to the container.
 */
export function useFocusTrap(containerRef) {
  // Read once, before the modal takes focus, so the opener is remembered.
  const [opener] = useState(() => (typeof document === "undefined" ? null : document.activeElement));

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    container.focus({ preventScroll: true });

    const wrapTab = (event) => {
      if (event.key !== "Tab") return;
      const stops = tabbableInside(container);
      if (stops.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }
      const first = stops[0];
      const last = stops[stops.length - 1];
      const active = document.activeElement;
      const outside = !container.contains(active) || active === container;
      if (event.shiftKey && (active === first || outside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || outside)) {
        event.preventDefault();
        first.focus();
      }
    };
    const pullBack = (event) => {
      if (!container.contains(event.target)) container.focus({ preventScroll: true });
    };

    document.addEventListener("keydown", wrapTab);
    document.addEventListener("focusin", pullBack);
    return () => {
      document.removeEventListener("keydown", wrapTab);
      document.removeEventListener("focusin", pullBack);
      if (opener && opener.isConnected && typeof opener.focus === "function") {
        opener.focus({ preventScroll: true });
      }
    };
  }, [containerRef, opener]);
}
