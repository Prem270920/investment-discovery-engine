/**
 * Inline SVG price chart
 * The forecast is drawn DASHED with a shaded confidence band
 */
import { useRef, useState } from "react";

export default function PriceChart({ points, forecast, currency }) {
  const svgRef = useRef(null);
  const [hover, setHover] = useState(null);   // index into the combined series

  if (!points || points.length < 2) {
    return <p style={{ color: "var(--ink-muted)" }}>No price history available.</p>;
  }

  const fPoints = forecast?.points ?? [];
  const w = 560, h = 170, pad = 6;

  const histCloses = points.map((p) => p.close);
  const allValues = [
    ...histCloses,
    ...fPoints.map((p) => p.lower),
    ...fPoints.map((p) => p.upper),
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
    ...fPoints.map((p) => ({
      value: p.predicted, date: p.date, isForecast: true,
      lower: p.lower, upper: p.upper,
    })),
  ];

  const histLine = histCloses
    .map((c, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(c).toFixed(1)}`)
    .join(" ");
  const histArea = `${histLine} L ${x(points.length - 1).toFixed(1)} ${h} L ${x(0).toFixed(1)} ${h} Z`;

  let forecastLine = "";
  let bandPath = "";
  if (fPoints.length) {
    const startX = x(points.length - 1);
    const startY = y(histCloses[histCloses.length - 1]);

    forecastLine = `M ${startX.toFixed(1)} ${startY.toFixed(1)} ` +
      fPoints.map((p, i) =>
        `L ${x(points.length + i).toFixed(1)} ${y(p.predicted).toFixed(1)}`
      ).join(" ");

    const upper = fPoints.map((p, i) =>
      `L ${x(points.length + i).toFixed(1)} ${y(p.upper).toFixed(1)}`).join(" ");
    const lower = [...fPoints].reverse().map((p, i) =>
      `L ${x(total - 1 - i).toFixed(1)} ${y(p.lower).toFixed(1)}`).join(" ");
    bandPath = `M ${startX.toFixed(1)} ${startY.toFixed(1)} ${upper} ${lower} Z`;
  }

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

  // Flip the label to the left near the right edge so it never clips.
  const labelW = 104;
  const flip = hoverX + labelW + 8 > w;
  const labelX = flip ? hoverX - labelW - 8 : hoverX + 8;

  const first = histCloses[0];
  const last = histCloses[histCloses.length - 1];
  const up = last >= first;
  const changePct = ((last - first) / first) * 100;

  return (
    <div>
      <svg
        ref={svgRef}
        width="100%"
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
        style={{ cursor: "crosshair" }}
        aria-label={`Price chart, ${changePct.toFixed(1)} percent ${up ? "up" : "down"} over one year${fPoints.length ? ", with projection" : ""}`}
      >
        <defs>
          <linearGradient id="histFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        <path d={histArea} fill="url(#histFill)" />
        {bandPath && <path d={bandPath} fill="var(--ink-muted)" opacity="0.18" />}
        <path d={histLine} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
        {forecastLine && (
          <path d={forecastLine} fill="none" stroke="var(--ink-muted)"
                strokeWidth="1.8" strokeDasharray="4 3" strokeLinejoin="round" />
        )}
        {fPoints.length > 0 && (
          <line x1={x(points.length - 1)} y1={pad} x2={x(points.length - 1)} y2={h - pad}
                stroke="var(--hairline)" strokeWidth="1" strokeDasharray="2 3" />
        )}

        {/* Hover readout */}
        {hovered && (
          <g pointerEvents="none">
            <line x1={hoverX} y1={pad} x2={hoverX} y2={h - pad}
                  stroke="var(--ink-muted)" strokeWidth="1" opacity="0.45" />
            <circle cx={hoverX} cy={hoverY} r="4"
                    fill={hovered.isForecast ? "var(--ink-muted)" : "var(--accent)"}
                    stroke="var(--bg-panel)" strokeWidth="2" />
            <rect x={labelX} y={Math.max(pad, hoverY - 30)} width={labelW} height="34"
                  rx="6" fill="var(--bg-deep)" stroke="var(--hairline)" />
            <text x={labelX + 8} y={Math.max(pad, hoverY - 30) + 14}
                  fill="var(--ink)" fontSize="12" fontWeight="600"
                  style={{ fontVariantNumeric: "tabular-nums" }}>
              {currency} {hovered.value.toFixed(2)}
            </text>
            <text x={labelX + 8} y={Math.max(pad, hoverY - 30) + 27}
                  fill="var(--ink-muted)" fontSize="10">
              {hovered.date}{hovered.isForecast ? " (projected)" : ""}
            </text>
          </g>
        )}
      </svg>

      <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "6px 0 0" }}>
        1 year:{" "}
        <span className="tnum" style={{
          color: up ? "var(--risk-very-low)" : "var(--risk-very-high)",
          fontWeight: 600,
        }}>
          {up ? "+" : ""}{changePct.toFixed(1)}%
        </span>{" "}
        ({currency} {first.toFixed(2)} → {last.toFixed(2)})
      </p>
    </div>
  );
}