import { useEffect, useState, useCallback } from "react";
import { getCarousels } from "./api";
import Carousel from "./components/Carousel";
import KnowledgeCard from "./components/KnowledgeCard";
import MarketFilter from "./components/MarketFilter";
import styles from "./App.module.css";
import SearchBar from "./components/SearchBar";
import BenchmarkHero from "./components/BenchmarkHero";

// Which index the hero shows for each market filter, and why it matters.
// Matches the stored data: Australian assets measure beta against ^AXJO,
// US and global assets against ^GSPC.
const BACKDROP_FOR_MARKET = {
  AU: { symbol: "^AXJO", note: "Every Australian asset below measures its beta against this index." },
  US: { symbol: "^GSPC", note: "Every US asset below measures its beta against this index." },
  GLOBAL: { symbol: "^GSPC", note: "Every global asset below measures its beta against this index." },
};
const DEFAULT_BACKDROP = {
  symbol: "^GSPC",
  note: "US and global assets below measure their beta against this index; Australian assets use the S&P/ASX 200.",
};

function App() {
  const [carousels, setCarousels] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [market, setMarket] = useState(null);   // null = all markets
  const [loading, setLoading] = useState(false);

  const fetchCarousels = useCallback((underlyingMarket) => {
    // min_size=3 hides the 2-asset stub carousel from the main dashboard
    return getCarousels(underlyingMarket, 3)
      .then((data) => setCarousels(data.carousels))
      .catch((err) => setError(err.message));
  }, []);

  // First load only. The loading flag is left alone here: it only dims
  // carousels already on screen, and there are none yet.
  useEffect(() => { fetchCarousels(null); }, [fetchCarousels]);

  // Later loads start from the click that asks for them. Re-clicking the
  // active tab changes nothing, so it fetches nothing, as before.
  const handleMarketChange = (value) => {
    if (value === market) return;
    setError(null);
    setMarket(value);
    setLoading(true);
    fetchCarousels(value).finally(() => setLoading(false));
  };

  if (error) {
    return (
      <div className={styles.state}>
        <h2>Couldn't reach the data service</h2>
        <p className={styles.stateDetail}>{error}</p>
        <p className={styles.stateDetail}>
          Is the backend running? <code>uvicorn src.api.main:app --reload</code>
        </p>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <span className={styles.wordmark}>Discovery Engine</span>
        <div className={styles.searchSlot}>
          <SearchBar onSelectAsset={setSelected} />
        </div>
        <span className={styles.tagline}>
          <span>Educational tool.</span> <span>Not financial advice.</span>
        </span>
      </header>

      <div className={styles.controls}>
        <MarketFilter selected={market} onChange={handleMarketChange} />
      </div>

      <main className={styles.main}>
        <BenchmarkHero {...(BACKDROP_FOR_MARKET[market] ?? DEFAULT_BACKDROP)} />
        {!carousels ? (
          <div className={styles.state}>Loading your dashboard…</div>
        ) : carousels.length === 0 ? (
          <div className={styles.state}>
            No assets match this market filter.
          </div>
        ) : (
          <div style={{ opacity: loading ? 0.5 : 1, transition: "opacity 150ms" }}>
            {carousels.map((c) => (
              <Carousel
                key={c.cluster_id}
                carousel={c}
                onSelectAsset={setSelected}
              />
            ))}
          </div>
        )}
      </main>

      {selected && (
        <KnowledgeCard symbol={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

export default App;