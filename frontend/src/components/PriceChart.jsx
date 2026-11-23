/**
 * Inline SVG price chart, with optional projections after the history.
 * ARIMA's projection is dashed with a shaded band; the GRU's is dotted with
 * a lighter band and a dotted outline.
 *
 * Everything is in neutral greys: colour only ever means risk, so the
 * direction of a change is carried by its + or minus sign alone, and the
 * models are told apart by line style.
 */
import { useId, useRef, useState } from "react";
import { formatChange, percentChange } from "../benchmarkLine";
import { FORECAST_LINES } from "../forecastLines";
import styles from "./PriceChart.module.css";

/**
 * changeLabel names the period for the change line under the chart ("1 year");
 * pass null to leave that line out, as the projection view does.
 * description, if given, replaces the generated accessible label.
 *
 * projections is a list of { id: "arima" | "gru", points } drawn after the
 * history, all on the same future dates. The older forecast prop ({ points })
 * still works and is drawn as a single ARIMA projection.
 */
export default function PriceChart({ points, forecast, projections, currency, changeLabel = "1 year", description }) {
  const svgRef = useRef(null);
  const fillId = useId();
  const [hover, setHover] = useState(null);   // index into the combined series

  if (!points || points.length < 2) {
    return <p className={styles.empty}>No price history available.</p>;
  }

  const shownProjections = (projections ?? (forecast?.points?.length ? [{ id: "arima", points: forecast.points }] : []))
    .filter((projection) => projection.points.length > 0);
  // The first projection sets the future dates; they all share them.
  const fPoints = shownProjections[0]?.points ?? [];
  const w = 560, h = 170, pad = 6;

  const histCloses = points.map((p) => p.close);
  const allValues = [
    ...histCloses,
    ...shownProjections.flatMap((projection) => projection.points.flatMap((p) => [p.lower, p.upper])),
  ];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const span = max - min || 1;

  const total = points.length + fPoints.length;
  const x = (i) => pad + (i / (total - 1)) * (w - pad * 2);
  const y = (v) => h - pad - ((v - min) / span) * (h - pad * 2);

  // One flat array so hover indexing works across history AND forecast.
  const series = [
    ...points.map((p) => ({
      value: p.close, date: p.date, isForecast: false,
    })),
    ...fPoints.map((p, i) => ({
      value: p.predicted, date: p.date, isForecast: true,
      lensValues: shownProjections.map((projection) => ({ id: projection.id, value: projection.points[i].predicted })),
    })),
  ];

  const histLine = histCloses
    .map((c, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(c).toFixed(1)}`)
    .join(" ");
  const histArea = `${histLine} L ${x(points.length - 1).toFixed(1)} ${h} L ${x(0).toFixed(1)} ${h} Z`;

  // Every projection leaves from the last real close.
  const startX = x(points.length - 1);
  const startY = y(histCloses[histCloses.length - 1]);
  const drawnProjections = shownProjections.map((projection) => {
    const projected = projection.points;
    const line = `M ${startX.toFixed(1)} ${startY.toFixed(1)} ` +
      projected.map((p, i) => `L ${x(points.length + i).toFixed(1)} ${y(p.predicted).toFixed(1)}`).join(" ");
    const upperEdge = projected.map((p, i) => `L ${x(points.length + i).toFixed(1)} ${y(p.upper).toFixed(1)}`).join(" ");
    const lowerEdge = [...projected].reverse().map((p, i) =>
      `L ${x(points.length + projected.length - 1 - i).toFixed(1)} ${y(p.lower).toFixed(1)}`).join(" ");
    return {
      id: projection.id,
      style: FORECAST_LINES[projection.id] ?? FORECAST_LINES.arima,
      line,
      band: `M ${startX.toFixed(1)} ${startY.toFixed(1)} ${upperEdge} ${lowerEdge} Z`,
    };
  });

  /** Convert a mouse position to the nearest data index.
   *  The SVG scales to its container, so we map screen px back into viewBox
   *  units via the bounding rect before finding the closest point. */
  const handleMove = (event) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const vbX = ((event.clientX - rect.left) / rect.width) * w;
    const ratio = (vbX - pad) / (w - pad * 2);
    const idx = Math.round(ratio * (total - 1));
    setHover(Math.max(0, Math.min(total - 1, idx)));
  };

  const hovered = hover != null ? series[hover] : null;
  const hoverX = hover != null ? x(hover) : 0;
  const hoverY = hovered ? y(hovered.value) : 0;

  // With two models the readout names each one, so it needs more room.
  const lensReadout = hovered?.isForecast && hovered.lensValues.length > 1 ? hovered.lensValues : null;
  // Flip the label to the left near the right edge so it never clips.
  const labelW = lensReadout ? 132 : 104;
  const labelH = lensReadout ? 20 + lensReadout.length * 14 : 34;
  const flip = hoverX + labelW + 8 > w;
  const labelX = flip ? hoverX - labelW - 8 : hoverX + 8;

  const first = histCloses[0];
  const last = histCloses[histCloses.length - 1];
  const up = last >= first;
  const changePct = percentChange(first, last);

  const generatedLabel =
    `Price chart, ${Math.abs(changePct).toFixed(1)} percent ${up ? "up" : "down"} over one year` +
    (fPoints.length ? ", with projection" : "");

  return (
    <div>
      <svg
        ref={svgRef}
        width="100%"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
        className={styles.chart}
        aria-label={description ?? generatedLabel}
      >
        <defs>
          <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--data-line)" stopOpacity="0.14" />
            <stop offset="100%" stopColor="var(--data-line)" stopOpacity="0" />
          </linearGradient>
        </defs>

        <path d={histArea} fill={`url(#${fillId})`} />
        {drawnProjections.map((projection) => (
          // ARIMA's band is a plain shade; the GRU's is lighter with a dotted
          // edge, so the two ranges stay readable where they overlap.
          <path key={`band-${projection.id}`} d={projection.band} data-band={projection.id}
                fill={projection.id === "gru" ? projection.style.stroke : "var(--ink-muted)"}
                fillOpacity={projection.id === "gru" ? 0.1 : 0.18}
                stroke={projection.id === "gru" ? projection.style.stroke : "none"}
                strokeOpacity="0.55" strokeWidth="1" strokeDasharray={projection.id === "gru" ? "0.1 3" : undefined}
                strokeLinecap="round" />
        ))}
        <path d={histLine} fill="none" stroke={FORECAST_LINES.actual.stroke} strokeWidth="2" strokeLinejoin="round" />
        {drawnProjections.map((projection) => (
          <path key={`line-${projection.id}`} d={projection.line} data-lens={projection.id}
                fill="none" stroke={projection.style.stroke} strokeWidth={projection.style.width}
                strokeDasharray={projection.style.dash} strokeLinecap="round" strokeLinejoin="round" />
        ))}
        {fPoints.length > 0 && (
          <line x1={x(points.length - 1)} y1={pad} x2={x(points.length - 1)} y2={h - pad}
                stroke="var(--hairline)" strokeWidth="1" strokeDasharray="2 3" />
        )}

        {/* Hover readout */}
        {hovered && (
          <g pointerEvents="none">
            <line x1={hoverX} y1={pad} x2={hoverX} y2={h - pad}
                  stroke="var(--ink-muted)" strokeWidth="1" opacity="0.45" />
            {(lensReadout ?? [{ id: hovered.isForecast ? "arima" : "actual", value: hovered.value }]).map((reading) => (
              <circle key={reading.id} cx={hoverX} cy={y(reading.value)} r="4"
                      fill={hovered.isForecast ? (FORECAST_LINES[reading.id] ?? FORECAST_LINES.arima).stroke : "var(--data-line)"}
                      stroke="var(--bg-panel)" strokeWidth="2" />
            ))}
            <rect x={labelX} y={Math.max(pad, Math.min(h - pad - labelH, hoverY - 30))} width={labelW} height={labelH}
                  rx="6" fill="var(--bg-deep)" stroke="var(--hairline)" />
            {lensReadout ? (
              <>
                {lensReadout.map((reading, row) => (
                  <text key={reading.id} x={labelX + 8} y={Math.max(pad, Math.min(h - pad - labelH, hoverY - 30)) + 14 + row * 14}
                        fill="var(--ink)" fontSize="12" fontWeight="600"
                        style={{ fontVariantNumeric: "tabular-nums" }}>
                    {FORECAST_LINES[reading.id].label} {currency} {reading.value.toFixed(2)}
                  </text>
                ))}
                <text x={labelX + 8} y={Math.max(pad, Math.min(h - pad - labelH, hoverY - 30)) + 14 + lensReadout.length * 14}
                      fill="var(--ink-muted)" fontSize="10">
                  {hovered.date} (projected)
                </text>
              </>
            ) : (
              <>
                <text x={labelX + 8} y={Math.max(pad, hoverY - 30) + 14}
                      fill="var(--ink)" fontSize="12" fontWeight="600"
                      style={{ fontVariantNumeric: "tabular-nums" }}>
                  {currency} {hovered.value.toFixed(2)}
                </text>
                <text x={labelX + 8} y={Math.max(pad, hoverY - 30) + 27}
                      fill="var(--ink-muted)" fontSize="10">
                  {hovered.date}{hovered.isForecast ? " (projected)" : ""}
                </text>
              </>
            )}
          </g>
        )}
      </svg>

      {changeLabel && (
        <p className={styles.change} data-testid="chart-change">
          {changeLabel}:{" "}
          <span className={`${styles.changeValue} tnum`}>{formatChange(changePct)}</span>{" "}
          ({currency} {first.toFixed(2)} → {last.toFixed(2)})
        </p>
      )}
    </div>
  );
}
