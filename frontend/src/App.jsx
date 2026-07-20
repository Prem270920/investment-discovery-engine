import { useEffect, useState } from "react";
import { getCarousels } from "./api";
import AssetCard from "./components/AssetCard";

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

  // render 4 cards from the first carousel to verify AssetCard styling and risk badge mapping
  const sample = carousels[0]?.assets.slice(0, 4) ?? [];
  return (
    <div style={{ padding: 40, display: "flex", gap: 16, flexWrap: "wrap" }}>
      {sample.map((a) => (
        <AssetCard key={a.symbol} asset={a} onSelect={(s) => alert(s)} />
      ))}
    </div>
  );
}

export default App;