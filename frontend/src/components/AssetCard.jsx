import { useCallback, useId, useRef, useState } from "react";
import { formatChange, linePath, percentChange, scalePoints } from "../benchmarkLine";
import { riskStyle } from "../risk";
import InfoTip from "./InfoTip";
import RiskChip from "./RiskChip";
import styles from "./AssetCard.module.css";

export const SHARPE_EXPLAINER =
  "Return earned for each unit of risk. Negative means the asset lost money over the period.";

// The sparkline is drawn at exactly the size it renders (the card's inner
// width), so the stroke dash used to draw it in maps one to one.
const SPARK_WIDTH = 166;
const SPARK_HEIGHT = 28;

/**
 * One tile in a carousel: risk chip, symbol, name, sparkline, Sharpe.
 * Clicking it opens the Knowledge Card.
 *
 * Pointing at the card (hover, keyboard focus, or its dot on the risk spread
 * strip) draws in a sparkline of the last 90 trading days and lifts the
 * Sharpe figure slightly. Every number is on the card at rest, including the
 * change over that window; the motion only adds the shape of the trend.
 * The line is one neutral colour for every card: direction is in the sign.
 *
 * highlighted lights the card up when its dot on the strip is pointed at;
 * onHighlight reports the reverse, so the strip can light the dot.
 */
export default function AssetCard({ asset, onSelect, highlighted = false, onHighlight = () => {} }) {
  const tier = riskStyle(asset.risk_tier);
  const sharpeTipId = useId();
  const infoRef = useRef(null);
  const cardRef = useRef(null);
  const [tipPlace, setTipPlace] = useState(null);
  const hideTip = useCallback(() => setTipPlace(null), []);
  // Opens under the info mark; if it has to flip up, it clears the whole card.
  const showTip = () => {
    if (!infoRef.current || !cardRef.current) return;
    setTipPlace({ below: infoRef.current.getBoundingClientRect(), above: cardRef.current.getBoundingClientRect() });
  };

  const sharpe =
    asset.sharpe_ratio != null ? asset.sharpe_ratio.toFixed(2) : "n/a";

  const closes = asset.sparkline_closes ?? [];
  const spark = closes.length >= 2 ? scalePoints(closes, SPARK_WIDTH, SPARK_HEIGHT, 0.1) : null;
  // The API's window starts and ends on real closes, so this is the true change.
  const windowChange = spark ? percentChange(closes[0], closes[closes.length - 1]) : null;

  // Keyboard focus also opens the Sharpe explainer, since the info mark
  // inside the card can't take focus itself (a button can't hold a button).
  // A mouse click focuses the card too, but that shouldn't pop a tooltip.
  const onFocus = (event) => {
    onHighlight(asset.symbol);
    if (focusIsFromKeyboard(event.currentTarget)) showTip();
  };

  // A native tooltip with the full name, only when the name is cut short.
  const offerFullName = (event) => {
    const nameSpan = event.currentTarget;
    nameSpan.title = nameSpan.scrollWidth > nameSpan.clientWidth ? asset.short_name : "";
  };

  return (
    <button
      ref={cardRef}
      className={`${styles.card} ${highlighted ? styles.highlighted : ""}`}
      data-symbol={asset.symbol}
      onClick={() => onSelect(asset.symbol)}
      onMouseEnter={() => onHighlight(asset.symbol)}
      onMouseLeave={() => { onHighlight(null); hideTip(); }}
      onFocus={onFocus}
      onBlur={() => { onHighlight(null); hideTip(); }}
      aria-label={`${asset.symbol}, ${asset.short_name}, ${tier.label}. View details.`}
      aria-describedby={sharpeTipId}
    >
      <RiskChip riskTier={asset.risk_tier} />

      <span className={styles.symbol}>{asset.symbol}</span>
      <span className={styles.name} onMouseEnter={offerFullName} data-testid="card-name">
        {asset.short_name}
      </span>

      <svg
        className={styles.spark}
        viewBox={`0 0 ${SPARK_WIDTH} ${SPARK_HEIGHT}`}
        width={SPARK_WIDTH}
        height={SPARK_HEIGHT}
        aria-hidden="true"
        data-testid="card-sparkline"
      >
        {spark && (
          <path className={styles.sparkLine} d={linePath(spark.coords)} pathLength="1" />
        )}
      </svg>
      <span className={`${styles.sparkChange} tnum`} data-testid="card-change">
        {windowChange === null ? "No recent prices" : `${formatChange(windowChange)} in 90 trading days`}
      </span>

      <span className={styles.metric}>
        <span className={styles.metricLabel}>
          Sharpe
          <span
            ref={infoRef}
            className={styles.info}
            onMouseEnter={showTip}
            onMouseLeave={hideTip}
            aria-hidden="true"
            data-testid="sharpe-info"
          >
            i
          </span>
        </span>
        <span className={`${styles.metricValue} tnum`}>{sharpe}</span>
      </span>
      <span id={sharpeTipId} className={styles.visuallyHidden}>Sharpe ratio: {SHARPE_EXPLAINER}</span>

      <InfoTip anchor={tipPlace?.below ?? null} aboveAnchor={tipPlace?.above} text={SHARPE_EXPLAINER} onDismiss={hideTip} />
    </button>
  );
}

function focusIsFromKeyboard(element) {
  try {
    return element.matches(":focus-visible");
  } catch {
    // Browsers without :focus-visible: treat focus as keyboard focus, so the
    // explainer is never unreachable.
    return true;
  }
}
