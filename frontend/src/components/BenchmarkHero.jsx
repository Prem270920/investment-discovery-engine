import { useEffect, useId, useState } from "react";
import { getBenchmarkPrices } from "../api";
import {
  areaPath, formatChange, formatDate, formatLevel, linePath, nearestIndex, percentChange, scalePoints,
} from "../benchmarkLine";
import { useInView } from "../hooks/useInView";
import { useReducedMotion } from "../hooks/useReducedMotion";
import styles from "./BenchmarkHero.module.css";

// The chart is drawn in this coordinate box and stretched to the container's
// width; the line keeps its stroke width through vector-effect.
const CHART_WIDTH = 1000;
const CHART_HEIGHT = 200;
// Page Up / Page Down jump about a month of trading days.
const PAGE_STEP = 21;

/**
 * The market backdrop above the carousels: a year of a benchmark index,
 * drawn from stored prices. Pointing along the line (or pressing the arrow
 * keys while it has focus) scrubs to that day's date and level. The latest
 * level, the year's change and its range are always shown as text.
 *
 * Renders nothing if the benchmark can't be loaded, so the dashboard below
 * never depends on it.
 */
export default function BenchmarkHero({ symbol, note }) {
  const [loaded, setLoaded] = useState({ symbol: null, history: null, failed: false });
  const [scrub, setScrub] = useState({ symbol: null, index: null });
  const [drawnSymbol, setDrawnSymbol] = useState(null);
  const [chartRef, chartInView] = useInView({ threshold: 0.3 });
  const reducedMotion = useReducedMotion();
  const gradientId = useId();
  const titleId = useId();

  useEffect(() => {
    let live = true;
    getBenchmarkPrices(symbol, 365)
      .then((history) => live && setLoaded({ symbol, history, failed: false }))
      .catch(() => live && setLoaded({ symbol, history: null, failed: true }));
    return () => { live = false; };
  }, [symbol]);

  // The previous benchmark's line is never shown under the new one's name.
  const current = loaded.symbol === symbol ? loaded : null;
  const points = current?.history?.points ?? [];
  const hasLine = points.length >= 2;

  // The line draws itself in once it is on screen: it renders undrawn first,
  // then flips a frame later so the stroke has something to transition from.
  useEffect(() => {
    if (!hasLine || !chartInView) return undefined;
    const frame = requestAnimationFrame(() => setDrawnSymbol(symbol));
    return () => cancelAnimationFrame(frame);
  }, [hasLine, chartInView, symbol]);

  if (current && !hasLine) return null;

  const lastIndex = points.length - 1;
  const scrubIndex = scrub.symbol === symbol ? scrub.index : null;
  const shownIndex = scrubIndex !== null ? Math.min(scrubIndex, lastIndex) : lastIndex;
  const scrubTo = (index) => setScrub({ symbol, index: Math.min(Math.max(index, 0), lastIndex) });
  const stopScrubbing = () => setScrub({ symbol: null, index: null });
  const drawn = drawnSymbol === symbol || reducedMotion;

  let chartContent = null;
  let header = null;
  let chartAria = {};
  if (hasLine) {
    const closes = points.map((point) => point.close);
    const { coords, low, high } = scalePoints(closes, CHART_WIDTH, CHART_HEIGHT);
    const shownPoint = points[shownIndex];
    const scrubbing = scrubIndex !== null;
    const change = percentChange(closes[0], scrubbing ? shownPoint.close : closes[lastIndex]);
    const marker = coords[shownIndex];
    const markerLeft = `${(marker.x / CHART_WIDTH) * 100}%`;

    header = (
      <>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>The market backdrop</p>
          <h1 className={styles.title} id={titleId}>{current.history.name}</h1>
          <p className={styles.note}>{note}</p>
        </div>
        <div className={styles.readout}>
          <span className={`${styles.level} tnum`} data-testid="hero-level">{formatLevel(shownPoint.close)}</span>
          <span className={styles.readoutDetail}>
            <span className="tnum" data-testid="hero-date">{formatDate(shownPoint.date)}</span>
            <span className={`tnum ${change >= 0 ? styles.up : styles.down}`}>
              {formatChange(change)}
              <span className={styles.changeLabel}>{scrubbing ? " since the start" : " over the year"}</span>
            </span>
          </span>
          <span className={`${styles.range} tnum`}>
            Year range {formatLevel(low)} to {formatLevel(high)}
          </span>
        </div>
      </>
    );

    chartAria = {
      role: "slider",
      tabIndex: 0,
      "aria-label": `${current.history.name} over the past year. Use the arrow keys to move through the days.`,
      "aria-valuemin": 0,
      "aria-valuemax": lastIndex,
      "aria-valuenow": shownIndex,
      "aria-valuetext": `${formatDate(shownPoint.date)}: ${formatLevel(shownPoint.close)}`,
    };

    chartContent = (
      <>
        <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.16" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path className={styles.area} d={areaPath(coords, CHART_HEIGHT)} fill={`url(#${gradientId})`} />
          <path className={styles.line} d={linePath(coords)} />
        </svg>
        {/* Marker and guide are HTML so the stretched SVG can't squash them into ovals */}
        <span className={`${styles.guide} ${scrubbing ? styles.visible : ""}`} style={{ left: markerLeft }} aria-hidden="true" />
        <span
          className={styles.marker}
          style={{ left: markerLeft, top: `${(marker.y / CHART_HEIGHT) * 100}%` }}
          aria-hidden="true"
        />
      </>
    );
  }

  const onPointerMove = (event) => {
    if (!hasLine) return;
    const box = event.currentTarget.getBoundingClientRect();
    scrubTo(nearestIndex((event.clientX - box.left) / box.width, points.length));
  };

  const onKeyDown = (event) => {
    if (!hasLine) return;
    const moves = {
      ArrowLeft: shownIndex - 1, ArrowRight: shownIndex + 1,
      PageUp: shownIndex - PAGE_STEP, PageDown: shownIndex + PAGE_STEP,
      Home: 0, End: lastIndex,
    };
    if (event.key in moves) {
      event.preventDefault();
      scrubTo(moves[event.key]);
    } else if (event.key === "Escape") {
      stopScrubbing();
    }
  };

  // One tree for loading and loaded, so the chart element (and the observer
  // watching it) stays the same when the data arrives.
  return (
    <section
      className={`${styles.hero} ${hasLine ? "" : styles.waiting}`}
      aria-labelledby={hasLine ? titleId : undefined}
      aria-label={hasLine ? undefined : "Loading market backdrop"}
      aria-busy={!hasLine}
    >
      {header}
      <div
        ref={chartRef}
        className={`${styles.chart} ${drawn ? styles.drawn : ""}`}
        onPointerMove={onPointerMove}
        onPointerLeave={stopScrubbing}
        onKeyDown={onKeyDown}
        onBlur={stopScrubbing}
        data-testid="benchmark-chart"
        {...chartAria}
      >
        {chartContent}
      </div>
    </section>
  );
}
