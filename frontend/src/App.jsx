import { useEffect, useState } from "react";
import { getCarousels } from "./api";
import Carousel from "./components/Carousel";
import styles from "./App.module.css";
import KnowledgeCard from "./components/KnowledgeCard";

function App() {
  const [carousels, setCarousels] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    getCarousels()
      .then((data) => setCarousels(data.carousels))
      .catch((err) => setError(err.message));
  }, []);

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

  if (!carousels) {
    return <div className={styles.state}>Loading your dashboard…</div>;
  }

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <span className={styles.wordmark}>Discovery Engine</span>
        <span className={styles.tagline}>
          Educational tool — not financial advice
        </span>
      </header>

      <main className={styles.main}>
        {carousels.map((c) => (
          <Carousel
            key={c.cluster_id}
            carousel={c}
            onSelectAsset={setSelected}
          />
        ))}
      </main>

      {selected && (
        <KnowledgeCard symbol={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

export default App;