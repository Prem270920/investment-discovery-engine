/**
 * Inline SVG price chart
 * No chart library: 60 lines of SVG fully control, with a gradient fill and a subtle glow on the line
 */
export default function PriceChart({ points, currency }) {
  if (!points || points.length < 2) {
    return <p style={{ color: "var(--ink-muted)" }}>No price history available.</p>;
  }

  const w = 560, h = 160, pad = 6;
  const closes = points.map((p) => p.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1;

  const x = (i) => pad + (i / (points.length - 1)) * (w - pad * 2);
  const y = (c) => h - pad - ((c - min) / span) * (h - pad * 2);

  const line = closes.map((c, i) => `${i ? "L" : "M"} ${x(i).toFixed(1)} ${y(c).toFixed(1)}`).join(" ");
  const area = `${line} L ${x(closes.length - 1).toFixed(1)} ${h} L ${x(0).toFixed(1)} ${h} Z`;

  const first = closes[0], last = closes[closes.length - 1];
  const up = last >= first;
  const changePct = ((last - first) / first) * 100;

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} role="img"
           aria-label={`One year price chart, ${changePct.toFixed(1)} percent ${up ? "up" : "down"}`}>
        <defs>
          <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#fill)" />
        <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" />
      </svg>
      <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "6px 0 0" }}>
        1 year: <span className="tnum" style={{ color: up ? "var(--risk-very-low)" : "var(--risk-very-high)", fontWeight: 600 }}>
          {up ? "+" : ""}{changePct.toFixed(1)}%
        </span>{" "}({currency} {first.toFixed(2)} → {last.toFixed(2)})
      </p>
    </div>
  );
}