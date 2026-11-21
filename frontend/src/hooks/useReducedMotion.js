import { useEffect, useState } from "react";

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function prefersReducedMotion() {
  // No matchMedia (old browsers, tests): assume motion is fine, since the CSS
  // rule in tokens.css still turns transitions off if the user asked.
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

/**
 * True when the user has asked the OS for reduced motion.
 *
 * CSS already collapses transitions under this preference. This hook is for
 * motion driven from JavaScript (requestAnimationFrame, staged reveals),
 * which CSS can't reach. It follows the setting live, so toggling it in
 * system settings takes effect without a reload.
 */
export function useReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(prefersReducedMotion);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }
    const motionQuery = window.matchMedia(REDUCED_MOTION_QUERY);
    const followPreference = (change) => setReducedMotion(change.matches);
    motionQuery.addEventListener("change", followPreference);
    return () => motionQuery.removeEventListener("change", followPreference);
  }, []);

  return reducedMotion;
}
