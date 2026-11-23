import { riskStyle } from "../risk";
import { tierNumber } from "../riskSpread";
import styles from "./RiskChip.module.css";

/**
 * The plain risk label ("Very low risk" to "Very high risk") in its tier's
 * risk temperature colour. One of the few places colour appears on data,
 * because colour only ever means risk.
 */
export default function RiskChip({ riskTier, className = "" }) {
  const tierStep = tierNumber(riskTier);
  return (
    <span
      className={`${styles.chip} ${className}`}
      style={{ "--chip-color": tierStep ? `var(--risk-temp-${tierStep})` : "var(--ink-muted)" }}
    >
      {riskStyle(riskTier).label}
    </span>
  );
}
