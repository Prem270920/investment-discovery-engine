import AssetCard from "./AssetCard";
import VolatilityPulse from "./VolatilityPulse";
import styles from "./Carousel.module.css";

/**
 * One horizontal row of the dashboard: a Fraunces title, the volatility-pulse signature,
 * a member count, and a scroll-snapping strip of AssetCards.
 */
export default function Carousel({ carousel, onSelectAsset }) {
  const shown = carousel.assets.length;
  const total = carousel.size;

  return (
    <section className={styles.row} aria-label={carousel.label}>
      <header className={styles.header}>
        <div>
          <h2 className={styles.title}>{carousel.label}</h2>
          <VolatilityPulse volatility={carousel.avg_volatility} />
        </div>
        <span className={styles.count}>
          {shown === total ? `${total} assets` : `${shown} of ${total} assets`}
        </span>
      </header>

      <div className={styles.scroller} role="list">
        {carousel.assets.map((asset) => (
          <AssetCard key={asset.symbol} asset={asset} onSelect={onSelectAsset} />
        ))}
      </div>
    </section>
  );
}