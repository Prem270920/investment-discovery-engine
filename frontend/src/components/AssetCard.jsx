import { riskStyle } from "../risk";
import styles from "./AssetCard.module.css";

/**
 * One tile in a carousel: risk badge, symbol, name, one metric.
 * Clicking it opens the Knowledge Card
 *
 * The risk badge reflects the backend's quantile risk_tier
 */
export default function AssetCard({ asset, onSelect }) {
  const tier = riskStyle(asset.risk_tier);
  
  const sharpe =
    asset.sharpe_ratio != null ? asset.sharpe_ratio.toFixed(2) : "—";

  return (
    <button
      className={styles.card}
      onClick={() => onSelect(asset.symbol)}
      aria-label={`${asset.symbol}, ${tier.label}. View details.`}
    >
      <span className={styles.badge}>
        <span
          className={styles.dot}
          style={{ background: tier.color }}
          aria-hidden="true"
        />
        <span className={styles.badgeLabel}>{tier.label}</span>
      </span>

      <span className={styles.symbol}>{asset.symbol}</span>
      <span className={styles.name} title={asset.short_name}>
        {asset.short_name}
      </span>

      <span className={styles.metric}>
        <span className={styles.metricLabel}>Sharpe</span>
        <span className={`${styles.metricValue} tnum`}>{sharpe}</span>
      </span>
    </button>
  );
}