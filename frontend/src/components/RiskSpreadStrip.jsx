import { useInView } from "../hooks/useInView";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { riskStyle } from "../risk";
import { layoutDots, spreadCaption, tierWord } from "../riskSpread";
import styles from "./RiskSpreadStrip.module.css";

// Geometry in px. Four dots fit across one segment; a fifth stacks above.
const SEGMENT_WIDTH = 52;
const SEGMENT_GAP = 3;
const DOT_SIZE = 8;
const DOT_PITCH = 11;
const DOTS_PER_ROW = 4;
const TRACK_HEIGHT = 4;
const DOT_TRACK_GAP = 5;
const STAGGER_MS = 25;
const STAGGER_CAP_MS = 400;

const PLOT_WIDTH = 5 * SEGMENT_WIDTH + 4 * SEGMENT_GAP;
const ROW_SPAN = DOTS_PER_ROW * DOT_PITCH - (DOT_PITCH - DOT_SIZE);
const ROW_INSET = (SEGMENT_WIDTH - ROW_SPAN) / 2;

/**
 * Where a carousel's assets sit on the five step risk scale, one dot per
 * asset. Hovering a dot highlights its card and clicking opens it; pointing
 * at a card (hover or keyboard focus) highlights its dot. The dots stay out
 * of the tab order: each one duplicates a card that is already a tab stop,
 * so keyboard users reach the same highlight from the card without 56 extra
 * stops. The dots slide in from the Calm end the first time the strip
 * scrolls into view.
 */
export default function RiskSpreadStrip({ assets, highlightedSymbol, onHighlight, onSelectAsset }) {
  const [plotRef, plotInView] = useInView({ threshold: 0.6 });
  const reducedMotion = useReducedMotion();
  const revealed = plotInView || reducedMotion;

  const { dots, rows } = layoutDots(assets, DOTS_PER_ROW);
  const caption = spreadCaption(assets);
  const stackHeight = Math.max(rows, 1) * DOT_PITCH - (DOT_PITCH - DOT_SIZE);
  const plotHeight = stackHeight + DOT_TRACK_GAP + TRACK_HEIGHT;

  return (
    <div className={styles.strip} role="group" aria-label={`Risk spread: ${caption}`}>
      <div className={styles.scale}>
        <div
          ref={plotRef}
          className={`${styles.plot} ${revealed ? styles.revealed : ""}`}
          style={{ width: PLOT_WIDTH, height: plotHeight }}
          data-testid="spread-plot"
        >
          {dots.map((dot, order) => {
            const left = (dot.tier - 1) * (SEGMENT_WIDTH + SEGMENT_GAP) + ROW_INSET + dot.column * DOT_PITCH;
            const top = stackHeight - DOT_SIZE - dot.row * DOT_PITCH;
            const highlighted = dot.symbol === highlightedSymbol;
            const asset = assets.find((candidate) => candidate.symbol === dot.symbol);
            return (
              <button
                key={dot.symbol}
                type="button"
                tabIndex={-1}
                className={`${styles.dot} ${highlighted ? styles.highlighted : ""}`}
                style={{
                  left,
                  top,
                  "--dot-color": `var(--risk-temp-${dot.tier})`,
                  // Slides in from the Calm end, so the travel itself shows how risky it is.
                  "--slide-from": `${-left}px`,
                  "--reveal-delay": `${Math.min(order * STAGGER_MS, STAGGER_CAP_MS)}ms`,
                }}
                aria-label={`${dot.symbol}: ${tierWord(dot.tier)}, ${riskStyle(asset.risk_tier).label.toLowerCase()}. Open details.`}
                data-symbol={dot.symbol}
                onMouseEnter={() => onHighlight(dot.symbol)}
                onMouseLeave={() => onHighlight(null)}
                onFocus={() => onHighlight(dot.symbol)}
                onBlur={() => onHighlight(null)}
                onClick={() => onSelectAsset(dot.symbol)}
              />
            );
          })}
          <div className={styles.track} style={{ top: stackHeight + DOT_TRACK_GAP, height: TRACK_HEIGHT }} aria-hidden="true">
            {[1, 2, 3, 4, 5].map((tier) => (
              <span key={tier} className={styles.segment} style={{ width: SEGMENT_WIDTH, background: `var(--risk-temp-${tier})` }} />
            ))}
          </div>
        </div>
        <div className={styles.ends} style={{ width: PLOT_WIDTH }} aria-hidden="true">
          <span>Calm</span>
          <span>Volatile</span>
        </div>
      </div>
      <p className={styles.caption}>{caption}</p>
    </div>
  );
}
