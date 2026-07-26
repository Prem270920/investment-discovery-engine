/**
 * Inline SVG price chart
 * The forecast is drawn DASHED with a shaded confidence band
 */
export default function PriceChart({ points, forecast, currency }) {
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

  // Historical line + fill
  const histLine = histCloses
    .map((c, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(c).toFixed(1)}`)
    .join(" ");
  const histArea = `${histLine} L ${x(points.length - 1).toFixed(1)} ${h} L ${x(0).toFixed(1)} ${h} Z`;

  // Forecast: start from the last real price so the line is continuous.
  let forecastLine = "";
  let bandPath = "";
  if (fPoints.length) {
    const startX = x(points.length - 1);
    const startY = y(histCloses[histCloses.length - 1]);

    forecastLine = `M ${startX.toFixed(1)} ${startY.toFixed(1)} ` +
      fPoints.map((p, i) =>
        `L ${x(points.length + i).toFixed(1)} ${y(p.predicted).toFixed(1)}`
      ).join(" ");

    // Band: trace the upper bound forward, then the lower bound back.
    const upper = fPoints.map((p, i) =>
      `L ${x(points.length + i).toFixed(1)} ${y(p.upper).toFixed(1)}`).join(" ");
    const lower = [...fPoints].reverse().map((p, i) =>
      `L ${x(total - 1 - i).toFixed(1)} ${y(p.lower).toFixed(1)}`).join(" ");
    bandPath = `M ${startX.toFixed(1)} ${startY.toFixed(1)} ${upper} ${lower} Z`;
  }

  const first = histCloses[0];
  const last = histCloses[histCloses.length - 1];
  const up = last >= first;
  const changePct = ((last - first) / first) * 100;

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} role="img"
           aria-label={`Price chart, ${changePct.toFixed(1)} percent ${up ? "up" : "down"} over one year${fPoints.length ? ", with projection" : ""}`}>
        <defs>
          <linearGradient id="histFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        <path d={histArea} fill="url(#histFill)" />

        {/* Uncertainty band — drawn first so the line sits on top */}
        {bandPath && (
          <path d={bandPath} fill="var(--ink-muted)" opacity="0.18" />
        )}

        <path d={histLine} fill="none" stroke="var(--accent)" strokeWidth="2"
              strokeLinejoin="round" />

        {/* Dashed = projection, visually distinct from real data */}
        {forecastLine && (
          <path d={forecastLine} fill="none" stroke="var(--ink-muted)"
                strokeWidth="1.8" strokeDasharray="4 3" strokeLinejoin="round" />
        )}

        {/* Divider marking where measured data ends and projection begins */}
        {fPoints.length > 0 && (
          <line x1={x(points.length - 1)} y1={pad} x2={x(points.length - 1)} y2={h - pad}
                stroke="var(--hairline)" strokeWidth="1" strokeDasharray="2 3" />
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