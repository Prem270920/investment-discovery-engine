import { FORECAST_LINES } from "../forecastLines";
import { LENS_NAMES } from "../headToHead";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { useReplay } from "../hooks/useReplay";
import LineKey from "./LineKey";
import styles from "./BacktestRace.module.css";

// About three seconds for the whole 30 days: long enough to follow the gaps
// opening and closing, short enough not to feel like waiting.
export const REPLAY_DURATION_MS = 3000;

const CHART_WIDTH = 560;
const CHART_HEIGHT = 170;
const CHART_PAD = 8;

/** The value at a fractional day, so lines advance smoothly between days. */
function valueAt(values, dayPosition) {
  const before = Math.floor(dayPosition);
  const after = Math.min(values.length - 1, before + 1);
  const between = dayPosition - before;
  return values[before] + (values[after] - values[before]) * between;
}

/**
 * The 30 day test, replayed. Each model was trained without the last 30
 * trading days and asked to predict them; this draws what really happened
 * and what each model said, day by day, at the same pace.
 *
 * At rest it shows the finished race, so every number is there without
 * pressing anything. "Replay the test" rewinds and draws it again, with a
 * gap marker at the leading edge showing how far each model is from the real
 * price. children (the head to head line) sit under the chart and fade in
 * again each time a replay finishes.
 */
export default function BacktestRace({ backtest, children }) {
  const reducedMotion = useReducedMotion();
  const { progress, playing, finishedCount, start } = useReplay(REPLAY_DURATION_MS, reducedMotion);

  const modelIds = ["arima", "gru"].filter((modelId) => backtest[modelId]);
  const dayCount = backtest.actual.length;
  const lastDay = dayCount - 1;
  const leadingDay = progress * lastDay;

  const everyValue = [backtest.actual, ...modelIds.map((modelId) => backtest[modelId])].flat();
  const lowest = Math.min(...everyValue);
  const valueSpan = Math.max(...everyValue) - lowest || 1;
  const xAt = (dayPosition) => CHART_PAD + (dayPosition / lastDay) * (CHART_WIDTH - CHART_PAD * 2);
  const yAt = (price) => CHART_HEIGHT - CHART_PAD - ((price - lowest) / valueSpan) * (CHART_HEIGHT - CHART_PAD * 2);

  // The line so far: every whole day passed, then the point it has reached.
  const lineSoFar = (values) => {
    const wholeDays = Math.floor(leadingDay);
    const corners = values.slice(0, wholeDays + 1).map((price, day) => [xAt(day), yAt(price)]);
    if (leadingDay > wholeDays) corners.push([xAt(leadingDay), yAt(valueAt(values, leadingDay))]);
    return corners.map(([cornerX, cornerY], position) =>
      `${position ? "L" : "M"} ${cornerX.toFixed(1)} ${cornerY.toFixed(1)}`).join(" ");
  };

  const realNow = valueAt(backtest.actual, leadingDay);
  const gaps = modelIds.map((modelId) => {
    const predictedNow = valueAt(backtest[modelId], leadingDay);
    return { modelId, predictedNow, gapPct: (Math.abs(predictedNow - realNow) / realNow) * 100 };
  });
  const edgeX = xAt(leadingDay);
  const dayLabel = playing ? `Day ${Math.min(dayCount, Math.floor(leadingDay) + 1)} of ${dayCount}` : `Day ${dayCount}, the last test day`;

  const modelWords = modelIds.map((modelId) => LENS_NAMES[modelId]).join(" and ");

  return (
    <div className={styles.race}>
      <LineKey lineIds={["actual", ...modelIds]}
               labels={{ arima: "ARIMA prediction", gru: "GRU prediction" }} />
      <svg
        className={styles.chart}
        width="100%"
        viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
        role="img"
        aria-label={`Backtest replay: the real price over ${dayCount} held out days, with ${modelWords} predictions for the same days`}
        data-testid="backtest-chart"
      >
        {gaps.map(({ modelId, predictedNow }) => (
          // The gap marker: how far this model is from the real price right now.
          <line key={`gap-${modelId}`} data-gap={modelId}
                x1={edgeX} y1={yAt(realNow)} x2={edgeX} y2={yAt(predictedNow)}
                stroke={FORECAST_LINES[modelId].stroke} strokeWidth="1" strokeOpacity="0.7" />
        ))}
        <path d={lineSoFar(backtest.actual)} data-line="actual" fill="none"
              stroke={FORECAST_LINES.actual.stroke} strokeWidth={FORECAST_LINES.actual.width}
              strokeLinejoin="round" strokeLinecap="round" />
        {modelIds.map((modelId) => (
          <path key={modelId} d={lineSoFar(backtest[modelId])} data-line={modelId} fill="none"
                stroke={FORECAST_LINES[modelId].stroke} strokeWidth={FORECAST_LINES[modelId].width}
                strokeDasharray={FORECAST_LINES[modelId].dash} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {gaps.map(({ modelId, predictedNow }) => (
          <circle key={`edge-${modelId}`} cx={edgeX} cy={yAt(predictedNow)} r="3"
                  fill="var(--bg-panel)" stroke={FORECAST_LINES[modelId].stroke} strokeWidth="1.5" />
        ))}
        <circle cx={edgeX} cy={yAt(realNow)} r="3.5" fill={FORECAST_LINES.actual.stroke}
                stroke="var(--bg-panel)" strokeWidth="1.5" />
      </svg>
      <div className={`${styles.axis} tnum`} aria-hidden="true">
        <span>{backtest.dates[0]}</span>
        <span>{backtest.dates[lastDay]}</span>
      </div>

      {/* Updated every frame while playing, so screen readers are spared the
          running commentary; the head to head line below carries the result. */}
      <p className={`${styles.readout} tnum`} aria-hidden={playing ? "true" : undefined} data-testid="gap-readout">
        <span className={styles.readoutDay}>{dayLabel}:</span>{" "}
        {gaps.map(({ modelId, gapPct }, position) => (
          <span key={modelId}>
            {position > 0 && ", "}
            {LENS_NAMES[modelId]} {gapPct.toFixed(1)}% from the real price
          </span>
        ))}
      </p>

      <button type="button" className={styles.replay} onClick={start}>
        Replay the test
      </button>

      <div key={finishedCount} className={finishedCount > 0 ? styles.appear : undefined} data-testid="race-summary">
        {children}
      </div>
    </div>
  );
}
