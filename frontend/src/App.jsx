import { useEffect, useState } from "react";
import { getCarousels } from "./api";

function App() {
  const [carousels, setCarousels] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getCarousels()
      .then((data) => setCarousels(data.carousels))
      .catch((err) => setError(err.message));
  }, []);

  if (error) {
    return (
      <div style={{ padding: 20, fontFamily: "monospace", color: "crimson" }}>
        <h2>API Error</h2>
        <p>{error}</p>
        <p>Is the backend running? Try: <code>uvicorn src.api.main:app --reload</code></p>
      </div>
    );
  }

  if (!carousels) {
    return <div style={{ padding: 20 }}>Loading carousels…</div>;
  }

  // Deliberately ugly: just prove the data arrives. Styling comes next.
  return (
    <div style={{ padding: 20, fontFamily: "system-ui" }}>
      <h1>Investment Discovery Engine</h1>
      <p>{carousels.length} carousels loaded from the API ✓</p>
      {carousels.map((c) => (
        <div key={c.cluster_id} style={{ marginBottom: 16 }}>
          <h3>{c.label} <small>({c.size} assets)</small></h3>
          <p style={{ color: "#666" }}>
            {c.assets.map((a) => a.symbol).join(", ")}
          </p>
        </div>
      ))}
    </div>
  );
}

export default App;