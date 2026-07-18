/**
 * Maps an asset's annualized volatility to a beginner-legible risk tier
 *
 * Fixed volatility bands: these thresholds are absolute,
 * not relative to the current universe. For a per-asset VISUAL BADGE that's
 * defensible — "high volatility" has a fairly stable intuitive meaning, and a
 * badge is a rough signal, not a precise claim. A future refinement could make
 * the bands relative to the dataset (see README "what I'd improve next").
 *
 * Bands chosen to map onto real data: bonds land very-low, broad ETFs
 * low/moderate, single growth stocks high/very-high.
 */
const TIERS = [
  { max: 0.06, label: "Very low risk", key: "very-low",  color: "var(--risk-very-low)" },
  { max: 0.12, label: "Low risk",      key: "low",       color: "var(--risk-low)" },
  { max: 0.20, label: "Moderate risk", key: "moderate",  color: "var(--risk-moderate)" },
  { max: 0.30, label: "High risk",     key: "high",      color: "var(--risk-high)" },
  { max: Infinity, label: "Very high risk", key: "very-high", color: "var(--risk-very-high)" },
];

export function riskTier(volatility) {
  // Null volatility (metric couldn't be computed) -> unknown, neutral styling.
  if (volatility == null) {
    return { label: "Risk unknown", key: "unknown", color: "var(--ink-muted)" };
  }
  return TIERS.find((t) => volatility < t.max);
}