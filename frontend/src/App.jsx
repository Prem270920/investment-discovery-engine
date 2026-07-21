import { useEffect, useState, useCallback } from "react";
import { getCarousels } from "./api";
import Carousel from "./components/Carousel";
import KnowledgeCard from "./components/KnowledgeCard";
import MarketFilter from "./components/MarketFilter";
import styles from "./App.module.css";

function App() {
  const [carousels, setCarousels] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [market, setMarket] = useState(null);   // null = all markets
  const [loading, setLoading] = useState(false);

  const load = useCallback((underlyingMarket) => {
    setLoading(true);
    // min_size=3 hides the 2-asset stub carousel from the main dashboard
    getCarousels(underlyingMarket, 3)
      .then((data) => setCarousels(data.carousels))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(market); }, [market, load]);

  const handleMarketChange = (value) => {
    setError(null);
    setMarket(value);
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
        <span className={styles.tagline}>
          Educational tool — not financial advice
        </span>
      </header>

      <div className={styles.controls}>
        <MarketFilter selected={market} onChange={handleMarketChange} />
      </div>

      <main className={styles.main}>
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