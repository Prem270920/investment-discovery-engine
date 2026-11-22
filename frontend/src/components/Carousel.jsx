import { useRef, useState } from "react";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { medianTier } from "../riskSpread";
import AssetCard from "./AssetCard";
import RiskSpreadStrip from "./RiskSpreadStrip";
import styles from "./Carousel.module.css";

// Room left beside a card scrolled in from off screen, so it doesn't sit flush
// against the scroller's edge.
const SCROLL_MARGIN = 16;

/**
 * One horizontal row of the dashboard: a Fraunces title, the risk spread
 * strip, a member count, and a scroll-snapping strip of AssetCards.
 *
 * The section is tinted, very faintly, with the risk temperature of its
 * middle asset, so the page warms as it moves from calm groups to volatile.
 */
export default function Carousel({ carousel, onSelectAsset }) {
  const shown = carousel.assets.length;
  const total = carousel.size;
  const scrollerRef = useRef(null);
  const reducedMotion = useReducedMotion();
  const [highlightedSymbol, setHighlightedSymbol] = useState(null);
  const sectionTier = medianTier(carousel.assets);

  // A dot can point at a card that is scrolled out of sight in the row; bring
  // it into view sideways, without moving the page up or down.
  const highlightFromDot = (symbol) => {
    setHighlightedSymbol(symbol);
    const scroller = scrollerRef.current;
    const card = symbol && scroller?.querySelector(`[data-symbol="${CSS.escape(symbol)}"]`);
    if (!card) return;
    const rowEdges = scroller.getBoundingClientRect();
    const cardEdges = card.getBoundingClientRect();
    let nudge = 0;
    if (cardEdges.left < rowEdges.left) nudge = cardEdges.left - rowEdges.left - SCROLL_MARGIN;
    else if (cardEdges.right > rowEdges.right) nudge = cardEdges.right - rowEdges.right + SCROLL_MARGIN;
    if (nudge !== 0) {
      scroller.scrollTo({ left: scroller.scrollLeft + nudge, behavior: reducedMotion ? "auto" : "smooth" });
    }
  };

  return (
    <section
      className={styles.row}
      aria-label={carousel.label}
      style={sectionTier ? { "--section-temp": `var(--risk-temp-${sectionTier})` } : undefined}
      data-median-tier={sectionTier ?? ""}
    >
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>{carousel.label}</h2>
          <RiskSpreadStrip
            assets={carousel.assets}
            highlightedSymbol={highlightedSymbol}
            onHighlight={highlightFromDot}
            onSelectAsset={onSelectAsset}
          />
        </div>
        <span className={styles.count}>
          {shown === total ? `${total} assets` : `${shown} of ${total} assets`}
        </span>
      </header>

      <div className={styles.scroller} role="list" ref={scrollerRef}>
        {carousel.assets.map((asset) => (
          <AssetCard
            key={asset.symbol}
            asset={asset}
            onSelect={onSelectAsset}
            highlighted={asset.symbol === highlightedSymbol}
            onHighlight={setHighlightedSymbol}
          />
        ))}
      </div>
    </section>
  );
}
