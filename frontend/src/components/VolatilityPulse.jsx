/**
 * The signature element: a thin "pulse" line under each carousel title whose
 * amplitude reflects the cluster's average volatility. 
 */
export default function VolatilityPulse({ volatility }) {
  const width = 120;
  const height = 18;
  const midY = height / 2;

  // Map volatility (~0.02 calm ... ~0.45 wild) to a peak amplitude in px.
  const vol = volatility ?? 0;
  const amplitude = Math.min(midY - 1, vol * 26);

  // Fixed 12-segment zigzag; amplitude alternates up/down.
  const segments = 12;
  const step = width / segments;
  let d = `M 0 ${midY}`;
  for (let i = 1; i <= segments; i++) {
    const x = i * step;
    const y = i % 2 === 1 ? midY - amplitude : midY + amplitude;
    d += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      style={{ display: "block" }}
    >
      <path
        d={d}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        opacity="0.7"
      />
    </svg>
  );
}