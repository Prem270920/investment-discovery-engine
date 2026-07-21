import styles from "./MarketFilter.module.css";

/**
 * Market/locality toggle. Re-fetches carousels filtered by underlying_market 
 */
const OPTIONS = [
  { value: null,     label: "All markets" },
  { value: "AU",     label: "Australia" },
  { value: "US",     label: "United States" },
  { value: "GLOBAL", label: "Global" },
];

export default function MarketFilter({ selected, onChange }) {
  return (
    <div className={styles.filter} role="tablist" aria-label="Filter by market">
      {OPTIONS.map((opt) => {
        const active = selected === opt.value;
        return (
          <button
            key={opt.label}
            role="tab"
            aria-selected={active}
            className={`${styles.tab} ${active ? styles.active : ""}`}
            onClick={() => onChange(opt.value)}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}