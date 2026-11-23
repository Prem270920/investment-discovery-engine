import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { getAsset, getPrices, getForecast, getDescription, getRelated } from "../api";
import { useCurrentSection } from "../hooks/useCurrentSection";
import { useFocusTrap } from "../hooks/useFocusTrap";
import { useInView } from "../hooks/useInView";
import { useReducedMotion } from "../hooks/useReducedMotion";
import OutlookSection from "./OutlookSection";
import PriceChart from "./PriceChart";
import RiskChip from "./RiskChip";
import styles from "./KnowledgeCard.module.css";

/** Plain-language explainer assembled from OUR OWN data. This is the FALLBACK used
 * when no NLP-derived description exists (ASX ETFs return no source text). */
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
      }. Where it's listed and what it owns are different things.`
    );
  }

  if (asset.beta != null && asset.benchmark_symbol) {
    const b = asset.beta;
    const bench = asset.benchmark_symbol === "^GSPC" ? "the S&P 500" : "the ASX 200";
    if (asset.currency === "AUD" && asset.benchmark_symbol === "^GSPC") {
      parts.push(
        `Its beta of ${b.toFixed(2)} against ${bench} looks low for what it holds. That's the currency effect: ` +
        `because it's priced in Australian dollars, movements in the AUD/USD exchange rate soften its relationship ` +
        `with the US market. This is what you actually experience holding it unhedged.`
      );
    } else if (b > 1.15) {
      parts.push(`With a beta of ${b.toFixed(2)}, it tends to amplify moves in ${bench}, with bigger gains in rallies and bigger falls in downturns.`);
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

// The four parts of the story, in reading order.
const STORY_SECTIONS = [
  { id: "about", label: "What is it" },
  { id: "moves", label: "How it moves" },
  { id: "outlook", label: "What might happen" },
  { id: "similar", label: "Similar assets" },
];
const SECTION_IDS = STORY_SECTIONS.map((section) => section.id);

// The projection view shows about three months of history before the
// forecast, so the 30 projected days aren't squeezed against a full year.
const PROJECTION_CONTEXT_DAYS = 63;

export const NOT_AVAILABLE = "Not available";

// One line of plain explanation under each metric.
const METRIC_NOTES = {
  volatility: "How much the price swings in a typical year. Higher means a bumpier ride.",
  sharpe: "Return earned for each unit of risk. Negative means the asset lost money over the period.",
  beta: "How strongly it moves with its benchmark. 1 moves in step, below 1 moves less.",
  dividend: "Yearly income paid out, as a share of the price.",
  pe: "Price divided by a year of earnings per share. Funds usually don't report one.",
  close: "The most recent closing price we have stored.",
};

// What the card holds before an asset has loaded: the loading state.
const EMPTY_CARD = {
  symbol: null, asset: null, prices: null, forecast: null,
  description: null, related: [], error: null,
};

/**
 * A full height panel that tells one asset's story in four parts: what it
 * is, how it moves, what might happen, and similar assets. A sticky index
 * shows where you are and jumps between parts. Sections fade up once as they
 * arrive; scrolling stays ordinary.
 *
 * While open, focus stays inside; Escape or the close button closes it, and
 * focus goes back to whatever opened it.
 */
export default function KnowledgeCard({ symbol, onClose }) {
  // The card controls its own active symbol, seeded from the prop, so clicking
  // a related asset navigates WITHIN the card (the Netflix browsing loop)
  // without the parent needing to know.
  const [activeSymbol, setActiveSymbol] = useState(symbol);

  // If the parent opens a different asset, respect that. Adjusted during
  // render rather than in an effect, so the card never paints a frame
  // still showing the previous asset's symbol.
  const [openedSymbol, setOpenedSymbol] = useState(symbol);
  if (symbol !== openedSymbol) {
    setOpenedSymbol(symbol);
    setActiveSymbol(symbol);
  }

  // Everything loaded for one asset, tagged with the symbol it belongs to.
  // Navigating changes activeSymbol, which makes the old content no longer
  // match, so the card falls back to its loading state without having to
  // clear anything first.
  const [loadedCard, setLoadedCard] = useState(EMPTY_CARD);
  const shownCard = loadedCard.symbol === activeSymbol ? loadedCard : EMPTY_CARD;
  const { asset, prices, forecast, description, related, error } = shownCard;

  const panelRef = useRef(null);
  const reducedMotion = useReducedMotion();
  useFocusTrap(panelRef);
  const [currentSection, jumpTo] = useCurrentSection(panelRef, SECTION_IDS, {
    contentKey: asset ? asset.symbol : null,
    reducedMotion,
  });

  useEffect(() => {
    let live = true;
    Promise.all([
      getAsset(activeSymbol),
      getPrices(activeSymbol, 365),
      getForecast(activeSymbol),
      getDescription(activeSymbol),
      getRelated(activeSymbol, 6),
    ])
      .then(([a, p, f, d, r]) => {
        if (live) {
          setLoadedCard({
            symbol: activeSymbol, asset: a, prices: p.points, forecast: f,
            description: d, related: r, error: null,
          });
        }
      })
      .catch((e) => live && setLoadedCard({ ...EMPTY_CARD, symbol: activeSymbol, error: e.message }));
    return () => { live = false; };
  }, [activeSymbol]);

  // On a phone the four labels are wider than the bar, so the index scrolls
  // sideways. Slide it so the highlighted entry is never hidden off the edge.
  // Moving the nav's own scrollLeft avoids scrollIntoView nudging the panel.
  const indexRef = useRef(null);
  useLayoutEffect(() => {
    const indexNav = indexRef.current;
    const currentButton = indexNav?.querySelector("[aria-current]");
    if (!indexNav || !currentButton) return;
    const navBox = indexNav.getBoundingClientRect();
    const buttonBox = currentButton.getBoundingClientRect();
    if (buttonBox.right > navBox.right) indexNav.scrollLeft += buttonBox.right - navBox.right;
    else if (buttonBox.left < navBox.left) indexNav.scrollLeft -= navBox.left - buttonBox.left;
  }, [currentSection]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // A related chip swaps the whole story, so start the new one from the top
  // and keep focus in the panel (the chip that had it is gone).
  const openRelated = (relatedSymbol) => {
    setActiveSymbol(relatedSymbol);
    const panel = panelRef.current;
    if (panel) {
      panel.scrollTo({ top: 0 });
      panel.focus({ preventScroll: true });
    }
  };

  const projectionHistory = prices ? prices.slice(-PROJECTION_CONTEXT_DAYS) : null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <article
        ref={panelRef}
        className={styles.panel}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={`${activeSymbol} details`}
        tabIndex={-1}
      >
        <div className={styles.bar} data-section-index>
          <nav ref={indexRef} className={styles.index} aria-label="Sections of this card">
            {STORY_SECTIONS.map((section) => (
              <button
                key={section.id}
                type="button"
                className={`${styles.indexItem} ${currentSection === section.id ? styles.indexCurrent : ""}`}
                aria-current={currentSection === section.id ? "true" : undefined}
                onClick={() => jumpTo(section.id)}
                disabled={!asset}
              >
                {section.label}
              </button>
            ))}
          </nav>
          <button className={styles.close} onClick={onClose} aria-label="Close">✕</button>
        </div>

        {error && <p className={styles.error}>{error}</p>}
        {!asset && !error && <p className={styles.loading}>Loading {activeSymbol}…</p>}

        {asset && (
          <>
            <StorySection id="about" label="What is it">
              <header className={styles.head}>
                <h2 className={styles.symbol}>{asset.symbol}</h2>
                <p className={styles.name}>{asset.short_name}</p>
                <div className={styles.badges}>
                  <RiskChip riskTier={asset.risk_tier} />
                  <span className={styles.pillMuted}>{asset.quote_type}</span>
                </div>
              </header>

              <h3 className={styles.explainerTitle}>What is this?</h3>
              {description ? (
                <>
                  <p className={styles.para}>{description.summary}</p>
                  {description.jargon.length > 0 && (
                    <JargonGlossary terms={description.jargon} />
                  )}
                </>
              ) : (
                explain(asset).map((p, i) => <p key={i} className={styles.para}>{p}</p>)
              )}
            </StorySection>

            <StorySection id="moves" label="How it moves">
              <PriceChart points={prices} currency={asset.currency} changeLabel="1 year" />

              <dl className={styles.metrics}>
                <Metric label="Volatility (1y)" note={METRIC_NOTES.volatility}
                        value={asset.annualized_volatility != null ? `${(asset.annualized_volatility * 100).toFixed(1)}%` : null} />
                <Metric label="Sharpe ratio" note={METRIC_NOTES.sharpe}
                        value={asset.sharpe_ratio?.toFixed(2)} />
                <Metric label={`Beta vs ${asset.benchmark_symbol ?? "benchmark"}`} note={METRIC_NOTES.beta}
                        value={asset.beta?.toFixed(2)} />
                <Metric label="Dividend yield" note={METRIC_NOTES.dividend}
                        value={asset.dividend_yield != null ? `${asset.dividend_yield.toFixed(2)}%` : null} />
                <Metric label="P/E ratio" note={METRIC_NOTES.pe}
                        value={asset.trailing_pe?.toFixed(1)} />
                <Metric label="Latest close" note={METRIC_NOTES.close}
                        value={`${asset.currency} ${asset.latest_close.toFixed(2)}`} />
              </dl>
            </StorySection>

            <StorySection id="outlook" label="What might happen">
              {forecast ? (
                // Keyed by asset so a related asset starts on ARIMA with a fresh replay.
                <OutlookSection key={asset.symbol} forecast={forecast}
                                history={projectionHistory} currency={asset.currency} />
              ) : (
                <p className={styles.para}>No projection is available for this asset yet.</p>
              )}
            </StorySection>

            <StorySection id="similar" label="Similar assets">
              <h3 className={styles.explainerTitle}>You might also like</h3>
              {related.length > 0 ? (
                <>
                  <p className={styles.relatedHint}>
                    Similar {asset.quote_type === "ETF" ? "funds" : "companies"}, ranked by how alike they behave.
                  </p>
                  <div className={styles.relatedRow}>
                    {related.map((r) => (
                      <button key={r.symbol} className={styles.relatedChip}
                              onClick={() => openRelated(r.symbol)}
                              aria-label={`${r.symbol}, ${r.short_name}. Open in this card.`}>
                        <span className={styles.relatedSymbol}>{r.symbol}</span>
                        <span className={styles.relatedName}>{r.short_name}</span>
                        <RiskChip riskTier={r.risk_tier} className={styles.relatedRisk} />
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <p className={styles.relatedHint}>No similar assets found.</p>
              )}
            </StorySection>

            <p className={styles.disclaimer}>
              Educational information only. Not financial advice.
            </p>
          </>
        )}
      </article>
    </div>
  );
}

/** One part of the story. Fades and rises in once, the first time it is seen. */
function StorySection({ id, label, children }) {
  const [sectionRef, inView] = useInView({ threshold: 0.15 });
  const reducedMotion = useReducedMotion();
  const headingId = `story-${id}`;
  return (
    <section
      ref={sectionRef}
      data-section={id}
      aria-labelledby={headingId}
      className={`${styles.section} ${inView || reducedMotion ? styles.revealed : ""}`}
    >
      <p className={styles.eyebrow} id={headingId}>{label}</p>
      {children}
    </section>
  );
}

function JargonGlossary({ terms }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.glossary}>
      <button className={styles.glossaryToggle} onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Hide" : "Explain the terms used"} ({terms.length})
      </button>
      {open && (
        <dl className={styles.glossaryList}>
          {terms.map((t) => (
            <div key={t.term} className={styles.glossaryItem}>
              <dt>{t.term}</dt>
              <dd>{t.plain}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function Metric({ label, value, note }) {
  return (
    <div className={styles.metric}>
      <dt className={styles.metricLabel}>{label}</dt>
      <dd className={`${styles.metricValue} ${value == null ? styles.missing : ""} tnum`}>{value ?? NOT_AVAILABLE}</dd>
      <dd className={styles.metricNote}>{note}</dd>
    </div>
  );
}
