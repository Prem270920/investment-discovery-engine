import { FORECAST_LINES } from "../forecastLines";
import styles from "./LineKey.module.css";

/**
 * Names each line on a chart next to a short sample of its style, so solid,
 * dashed and dotted can be matched to "Real price", "ARIMA" and "GRU"
 * without relying on colour.
 */
export default function LineKey({ lineIds, labels = {} }) {
  return (
    <ul className={styles.key} aria-label="Line key">
      {lineIds.map((lineId) => {
        const line = FORECAST_LINES[lineId];
        return (
          <li key={lineId} className={styles.entry} data-line={lineId}>
            <svg className={styles.sample} viewBox="0 0 28 8" width="28" height="8" aria-hidden="true">
              <line x1="2" y1="4" x2="26" y2="4" stroke={line.stroke} strokeWidth={line.width}
                    strokeDasharray={line.dash} strokeLinecap="round" />
            </svg>
            {labels[lineId] ?? line.label}
          </li>
        );
      })}
    </ul>
  );
}
