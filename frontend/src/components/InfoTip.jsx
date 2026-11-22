import { useEffect } from "react";
import { createPortal } from "react-dom";
import styles from "./InfoTip.module.css";

const TIP_WIDTH = 220;
const EDGE_GAP = 8;
// Room needed to open below the anchor; three lines of caption text.
const TIP_ROOM = 80;

/**
 * A small explanation floating just below an anchor rectangle. When the
 * window has no room underneath it flips above, clearing aboveAnchor (the
 * whole card, say) rather than just the anchor, so it never lands on card
 * content that sits above the anchor, such as a card's sparkline.
 *
 * Rendered into document.body with fixed positioning, because the cards it
 * explains sit in a sideways scrolling row that would clip anything poking
 * out of them. It is a visual copy only (aria-hidden): the owner points
 * aria-describedby at its own hidden text, so screen readers hear it once.
 *
 * Any scroll or resize closes it, since the anchor it was placed against
 * has moved.
 */
export default function InfoTip({ anchor, aboveAnchor = anchor, text, onDismiss }) {
  useEffect(() => {
    if (!anchor) return undefined;
    window.addEventListener("scroll", onDismiss, true);
    window.addEventListener("resize", onDismiss);
    return () => {
      window.removeEventListener("scroll", onDismiss, true);
      window.removeEventListener("resize", onDismiss);
    };
  }, [anchor, onDismiss]);

  if (!anchor) return null;

  // Centred over the anchor, but kept fully inside the window.
  const centre = anchor.left + anchor.width / 2;
  const half = TIP_WIDTH / 2;
  const left = Math.min(Math.max(centre, half + EDGE_GAP), window.innerWidth - half - EDGE_GAP);
  const opensBelow = anchor.bottom + EDGE_GAP + TIP_ROOM <= window.innerHeight;
  const top = opensBelow ? anchor.bottom + EDGE_GAP : aboveAnchor.top - EDGE_GAP;

  return createPortal(
    <div
      className={`${styles.tip} ${opensBelow ? styles.below : styles.above}`}
      role="tooltip"
      aria-hidden="true"
      data-placement={opensBelow ? "below" : "above"}
      style={{ left, top, width: TIP_WIDTH }}
    >
      {text}
    </div>,
    document.body,
  );
}
