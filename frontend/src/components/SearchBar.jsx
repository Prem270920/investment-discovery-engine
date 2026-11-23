import { useEffect, useRef, useState } from "react";
import { searchAssets } from "../api";
import { tierNumber } from "../riskSpread";
import styles from "./SearchBar.module.css";

/**
 * Search box with a live results dropdown. Debounced so we don't fire a request on every keystroke: it waits until typing pauses.
 */
export default function SearchBar({ onSelectAsset }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const boxRef = useRef(null);

  // Clearing the box drops old results straight away, in the same keystroke,
  // so typing again never flashes matches for the previous query.
  const handleQueryChange = (value) => {
    setQuery(value);
    if (!value.trim()) setResults([]);
  };

  // Debounce: only search 200ms after the last keystroke.
  useEffect(() => {
    if (!query.trim()) return;
    const timer = setTimeout(() => {
      searchAssets(query).then((r) => {
        setResults(r);
        setOpen(true);
      });
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  // Close the dropdown when clicking outside.
  useEffect(() => {
    const onClick = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, []);

  const pick = (symbol) => {
    onSelectAsset(symbol);
    setQuery("");
    setResults([]);
    setOpen(false);
  };

  return (
    <div className={styles.wrap} ref={boxRef}>
      <input
        className={styles.input}
        type="text"
        placeholder="Search a stock or fund…"
        value={query}
        onChange={(e) => handleQueryChange(e.target.value)}
        onFocus={() => results.length && setOpen(true)}
        aria-label="Search assets"
      />
      {open && results.length > 0 && (
        <ul className={styles.results} role="listbox">
          {results.map((a) => {
            // Same risk temperature step as the asset's chip, so a dot here
            // and a chip on the card never disagree about colour.
            const tierStep = tierNumber(a.risk_tier);
            const dotColour = tierStep ? `var(--risk-temp-${tierStep})` : "var(--ink-muted)";
            return (
              <li key={a.symbol}>
                <button className={styles.result} onClick={() => pick(a.symbol)}>
                  <span className={styles.dot} style={{ background: dotColour }} aria-hidden="true" />
                  <span className={styles.resultSymbol}>{a.symbol}</span>
                  <span className={styles.resultName}>{a.short_name}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {open && query.trim() && results.length === 0 && (
        <div className={styles.empty}>No matches for "{query}"</div>
      )}
    </div>
  );
}