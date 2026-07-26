import { useEffect, useState } from "react";
import { riskStyle } from "../risk";
import PriceChart from "./PriceChart";
import styles from "./KnowledgeCard.module.css";
import { getAsset, getPrices, getForecast } from "../api";

/** Plain-language explainer assembled from my own data — no NLP yet, 
 * The cross-currency beta case gets its own paragraph: the FX story is the app's best teaching moment */
function explain(asset) {
  const parts = [];

  const kind = asset.quote_type === "ETF"
    ? "a fund that holds many investments at once, so you're not betting on a single company"
    : "a share in a single company";
  const marketDesc = { AU: "Australian", US: "US", GLOBAL: "globally diversified" }[asset.underlying_market] ?? "";
  parts.push(`${asset.symbol} is ${kind}, with ${marketDesc} exposure.`);

  if (asset.listed_exchange === "ASX" && asset.underlying_market !== "AU") {
    parts.push(
      `Although it trades on the Australian stock exchange in AUD, what it actually holds is ${
        asset.underlying_market === "US" ? "US companies" : "companies from around the world"
      } — where it's listed and what it owns are different things.`
    );
  }

  if (asset.beta != null && asset.benchmark_symbol) {
    const b = asset.beta;
    const bench = asset.benchmark_symbol === "^GSPC" ? "the S&P 500" : "the ASX 200";
    if (asset.currency === "AUD" && asset.benchmark_symbol === "^GSPC") {
      parts.push(
        `Its beta of ${b.toFixed(2)} against ${bench} looks low for what it holds — that's the currency effect: ` +
        `because it's priced in Australian dollars, movements in the AUD/USD exchange rate soften its relationship ` +
        `with the US market. This is what you actually experience holding it unhedged.`
      );
    } else if (b > 1.15) {
      parts.push(`With a beta of ${b.toFixed(2)}, it tends to amplify moves in ${bench} — bigger gains in rallies, bigger falls in downturns.`);
    } else if (b < 0.3) {
      parts.push(`With a beta of ${b.toFixed(2)}, it moves largely independently of ${bench}.`);
    } else {
      parts.push(`Its beta of ${b.toFixed(2)} means it broadly follows ${bench}.`);
    }
  }

  if (asset.dividend_yield != null && asset.dividend_yield > 2.5) {
    parts.push(`It pays a meaningful income: a dividend yield around ${asset.dividend_yield.toFixed(1)}%.`);
  }

  return parts;
}

export default function KnowledgeCard({ symbol, onClose }) {
  const [asset, setAsset] = useState(null);
  const [prices, setPrices] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let live = true;
    Promise.all([getAsset(symbol), getPrices(symbol, 365), getForecast(symbol)])
      .then(([a, p, f]) => {
        if (live) { setAsset(a); setPrices(p.points); setForecast(f); }
      })
      .catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [symbol]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tier = asset ? riskStyle(asset.risk_tier) : null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <article className={styles.panel} onClick={(e) => e.stopPropagation()}
               role="dialog" aria-modal="true" aria-label={`${symbol} details`}>
        <button className={styles.close} onClick={onClose} aria-label="Close">✕</button>

        {error && <p className={styles.error}>{error}</p>}
        {!asset && !error && <p className={styles.loading}>Loading {symbol}…</p>}

        {asset && (
          <>
            <header className={styles.head}>
              <div>
                <h2 className={styles.symbol}>{asset.symbol}</h2>
                <p className={styles.name}>{asset.short_name}</p>
              </div>
              <div className={styles.badges}>
                <span className={styles.pill} style={{ borderColor: tier.color, color: tier.color }}>
                  {tier.label}
                </span>
                <span className={styles.pillMuted}>{asset.quote_type}</span>
              </div>
            </header>

            <PriceChart points={prices} forecast={forecast} currency={asset.currency} />

            {forecast && (
              <section className={styles.forecastNote}>
                <h3 className={styles.explainerTitle}>The dashed projection</h3>
                <p className={styles.para}>
                  The dashed line projects {forecast.horizon_days} trading days ahead
                  using an ARIMA model{" "}
                  {forecast.method === "returns"
                    ? "fitted to daily returns"
                    : "fitted to prices directly"}
                  . The shaded band shows the range of plausible outcomes — notice it
                  gets wider the further out it goes, because uncertainty compounds.
                </p>
                {forecast.backtest_error_pct != null && (
                  <p className={styles.para}>
                    <strong>How much should you trust it?</strong> Tested on the most
                    recent 30 days it had never seen, this model's projections were off
                    by about{" "}
                    <span className="tnum" style={{ color: "var(--ink)", fontWeight: 600 }}>
                      {forecast.backtest_error_pct}%
                    </span>
                    {" "}on average. Treat it as an illustration of a statistical trend —
                    not a prediction of what will happen.
                  </p>
                )}
              </section>
            )}

            <div className={styles.metrics}>
              <Metric label="Volatility (1y)" value={asset.annualized_volatility != null ? `${(asset.annualized_volatility * 100).toFixed(1)}%` : "—"} />
              <Metric label="Sharpe ratio" value={asset.sharpe_ratio?.toFixed(2) ?? "—"} />
              <Metric label={`Beta vs ${asset.benchmark_symbol ?? "—"}`} value={asset.beta?.toFixed(2) ?? "—"} />
              <Metric label="Dividend yield" value={asset.dividend_yield != null ? `${asset.dividend_yield.toFixed(2)}%` : "—"} />
              <Metric label="P/E ratio" value={asset.trailing_pe?.toFixed(1) ?? "—"} />
              <Metric label="Latest close" value={`${asset.currency} ${asset.latest_close.toFixed(2)}`} />
            </div>

            <section className={styles.explainer}>
              <h3 className={styles.explainerTitle}>What is this?</h3>
              {explain(asset).map((p, i) => <p key={i} className={styles.para}>{p}</p>)}
              <p className={styles.disclaimer}>
                Educational information only — not financial advice.
              </p>
            </section>
          </>
        )}
      </article>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className={styles.metric}>
      <span className={styles.metricLabel}>{label}</span>
      <span className={`${styles.metricValue} tnum`}>{value}</span>
    </div>
  );
}