/**
 * Presentation helper for risk tiers
 *
 * The RISK TIER itself is computed in the backend (quantile buckets of
 * volatility across the universe — view clustering.py)
 */

const TIER_STYLES = {
  "Very low":  { label: "Very low risk",  color: "var(--risk-very-low)" },
  "Low":       { label: "Low risk",       color: "var(--risk-low)" },
  "Moderate":  { label: "Moderate risk",  color: "var(--risk-moderate)" },
  "High":      { label: "High risk",      color: "var(--risk-high)" },
  "Very high": { label: "Very high risk", color: "var(--risk-very-high)" },
};

const UNKNOWN = { label: "Risk unknown", color: "var(--ink-muted)" };

export function riskStyle(riskTier) {
  return TIER_STYLES[riskTier] ?? UNKNOWN;
}
