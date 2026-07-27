# Investment Discovery Engine

A browsing tool for people who want to start investing and don't know where to look. Instead of a spreadsheet with 40 columns, it groups assets into themed rows — "Safe & Steady", "Income Generators", "Higher-Risk Growth" — and explains each one in plain English.

The categories aren't hand-written. They come out of a clustering model trained on risk behaviour, so an energy ETF can end up sitting next to Coca-Cola if that's how they actually move.

> **This is an educational tool, not financial advice.** Nothing here is a recommendation to buy anything. The price projections in particular are illustrations of a statistical trend, not predictions — more on that below.

---

## The problem I was actually solving

If you've never invested before, the hard part isn't the buying. It's that there are thousands of options, the data is scattered, and every source assumes you already know what beta means.

The manual version of this is what a curious beginner does over a weekend: look up some ETFs, try to figure out which ones are "safe", squint at a chart, give up. This automates that triage — pulls the data, computes the risk metrics, groups similar assets together, and writes the explanation.

Australia + US + global, because I'm in Melbourne and most tools are US-only.

---

## Running it

```bash
git clone https://github.com/Prem270920/investment-discovery-engine.git
cd investment-discovery-engine

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python -m src.pipeline --recreate    # ~90 seconds; pulls data, computes everything
uvicorn src.api.main:app --reload    # API on :8000, docs at /docs
```

Then in a second terminal:

```bash
cd frontend && npm install && npm run dev    # UI on :5173
```

The clustering model is committed to the repo (`models/cluster_model.joblib`), so you'll get the same six categories I did rather than whatever the market happened to be doing when you cloned it. If you want to retrain: `python -m src.ml.train_clusters`.

Add `--skip-forecasts` to the pipeline command for a faster run — the ARIMA stage is the slow part.

---

## How it fits together

```
yfinance  →  validate  →  SQLite  →  metrics  →  cluster  →  FastAPI  →  React
                ↓                       ↓           ↓
          override map            vol/Sharpe/beta  frozen
          for bad vendor data     ARIMA forecast   model
```

Everything is a batch job. The app never calls yfinance at request time — it reads from its own database. That means it stays up when Yahoo doesn't, and it isn't hostage to rate limits.

The pipeline runs five stages inside a single transaction: ingest assets, ingest benchmarks, compute metrics, assign clusters, generate forecasts. If any stage fails the whole thing rolls back, so you never end up with assets but no metrics.

**56 assets, ~14,000 price bars, six clusters.**

---

## Three things that went wrong

This is the part I'd actually want to talk about in an interview.

### The beta that was impossible

IVV.AX is an ASX-listed ETF that holds the S&P 500. Its US-listed twin, IVV, is literally the same fund. Measured against the S&P 500, IVV came out at beta 1.02 — correct. IVV.AX came out at **0.03**.

Not surprising. Impossible. A fund that holds the S&P 500 cannot be uncorrelated with the S&P 500. I only caught it because I had the twin sitting right there to compare against.

What followed was three hypotheses, each tested rather than assumed:

1. **Timezone misalignment.** The ASX closes before New York opens, so joining daily returns by calendar date compares different days' information. Resampling both to weekly moved beta from 0.03 → 0.34. Better, still wrong.
2. **Currency dilution.** IVV.AX is priced in AUD; the S&P 500 is in USD. Converting the prices to USD first moved it to 0.67. Better, still wrong.
3. **Inverted conversion.** Maybe I was multiplying where I should have divided? Tested both. Dividing gave a correlation of −0.007 — catastrophically worse. Hypothesis dead.

The test that settled it: comparing IVV.AX (converted to USD) against IVV directly. Same fund, same currency, so they should correlate ~0.99. They correlated **0.67**. Since the control — IVV against the index — came out at 0.996, the method was fine. The conversion was the broken link.

Root cause: yfinance's daily FX bar and the ASX equity close are snapped at different times of day. Multiplying them strips some of the currency effect while injecting fresh timing noise. **The free data can't support a clean currency conversion.**

So I stopped, and reported the FX-inclusive number instead. That's defensible because **0.33 is a real number** — an Australian holding an unhedged AUD-priced S&P 500 fund genuinely does not get 1:1 exposure to the S&P 500. Currency movements dilute it. That dilution is the investor's actual experience, not an artifact.

The app now explains this gap to the user on the asset page. What started as a bug became the best teaching moment in the product.

I later added IHVV.AX — the currency-*hedged* version of the same fund — as a natural experiment. Its beta came out roughly double the unhedged one, which supports the currency explanation without fully closing the gap. The rest is the timing effect I couldn't fix.

### Carousels that reshuffled every run

The first version refit KMeans on every pipeline run. Since it trains on live market data, and market data moves, the clusters redrew themselves each time. One run labelled the entire bond cluster "Recent Underperformers" — technically true (bonds had the worst Sharpe in a rising market) and completely useless as a category.

The fix was to separate training from inference, which is how this is supposed to work anyway. `train_clusters.py` fits the scaler and the model, derives the labels from the centroids, and saves all three as a versioned artifact. The pipeline loads that artifact and calls `.predict()` — never `.fit()`. Same model in, same categories out.

The labels are frozen inside the artifact too, which killed a second bug: the rules that assign human names to clusters were being re-evaluated each run against shifting centroids, so a category could silently change meaning between runs.

Rule ordering turned out to matter more than I expected. An early version claimed "Higher-Risk Growth" by highest volatility, which grabbed a two-asset cluster that was volatile because it had *crashed* (Sharpe −1.28). Growth now keys on beta, and "Safe & Steady" gets claimed before "Underperformers" so bonds don't get mislabelled in a bull market.

### A pipeline that lied about succeeding

The run summary printed `metrics computed: 56`. The database had zero rows.

During a refactor I'd lost the `session.commit()`. Every run staged its work, logged success, then closed the session and threw it all away. The logs cheerfully reported a completed run the entire time.

I found it by checking `SELECT COUNT(*)` instead of trusting the summary. That habit — verify the outcome, not the log — has caught more in this project than anything else.

---

## The forecasts, and why they're honest

Every asset page shows a 30-day price projection. I want to be direct about what that is.

Forecasting asset prices is not reliably possible. If it were, none of us would need jobs. So the goal was never accuracy — it was building something that shows its own uncertainty rather than hiding it.

Two things make it honest.

**The confidence band widens.** Uncertainty compounds: being unsure about tomorrow is very different from being unsure about six weeks out. Variance grows with the number of steps, so the band grows with √n. For VAS.AX it goes from 3.25 wide on day one to 18.01 by day thirty. You can watch it fan out. That's the lesson, delivered visually.

**Each forecast reports its own measured error.** I hold out the last 30 days, train on everything before that, and check how far off the projection was on data the model never saw. That number goes on the page: *"tested on 30 days it had never seen, this model was off by about 0.71%."*

The error tracks risk almost perfectly, which is the nicest validation of the whole thing:

| Asset | Backtest error |
|---|---|
| SHY (short treasuries) | 0.12% |
| BND (total bond market) | 0.53% |
| VOO (S&P 500) | 1.93% |
| AAPL | 5.11% |
| CSL.AX | 9.85% |

The model is measurably better at boring assets and worse at exciting ones. That isn't a disclaimer, it's evidence — "trust this less for TSLA" becomes something the app can *demonstrate* rather than assert.

Under the hood it fits two competing models per asset — ARIMA on prices and ARIMA on returns — with the order auto-selected by AIC, backtests both, and keeps whichever won. Across 56 assets the split was roughly 39 to 17, so both approaches are earning their place rather than one always winning.

---

## Decisions worth explaining

**Where an asset is listed isn't what it holds.** yfinance tells you IVV.AX trades on the ASX in AUD. It doesn't tell you it holds 500 American companies. A naive "`.AX` means Australian" rule mislabels it, and then the Australia filter shows you a US fund.

So there's a curated override map — but only for the exceptions. Eleven entries covering 56 assets. Individual stocks don't need one (an ASX-listed company *is* Australian); ETFs are the problem, because an ETF is a wrapper that can hold anything. The map is short enough to read in a glance, and every line documents a case where the obvious rule breaks.

**The universe is curated on purpose.** I could auto-fetch the ASX 200 and S&P 500 and have 700 assets. I deliberately didn't. The app exists because beginners can't navigate hundreds of options — dumping 700 on them recreates the exact problem it's meant to solve. Curation *is* the product. It's also the only way to keep the exposure labels correct, since nothing in the free data tells you what an unfamiliar ETF actually holds.

The list lives in `config/universe.yaml`, so scaling up is a config change rather than a code change.

**Risk metrics are computed, not fetched.** yfinance returns `beta = None` for every single ETF I tested. Since ETFs are most of what a beginner should be looking at, that field is useless. Volatility, Sharpe and beta are all computed from stored price history instead — works identically for funds and stocks, and I can explain exactly how each number was derived.

**Clustering doesn't see the labels.** The model gets volatility, Sharpe, beta and dividend yield. It does *not* get asset type, sector, or country, because then it would mostly rediscover the categories I already had. Leaving them out is why the "Market-Neutral Defensives" row contains a utilities ETF, an energy ETF, Johnson & Johnson and Coca-Cola — grouped only by the fact that they all move independently of the market. No conventional taxonomy puts those four together.

**The explainers are templated, not generated.** They read like prose but they're rule-based, assembled from the computed metrics. I considered an LLM and decided against it: in a finance tool aimed at beginners, a model that occasionally invents a fact is worse than one that's slightly stiff. Everything on the page traces back to a number in the database.

---

## Known limitations

- **Cross-currency beta is FX-inclusive.** Documented above. Fixing it properly needs FX rates snapped at market close, which the free feed doesn't provide.
- **Risk tiers are relative to this universe.** They're quintiles, so "Very low risk" means "among the calmest fifth of the 56 assets here", not an absolute claim about the market.
- **Cluster labels are heuristics.** Rules applied to centroids, ranked against each other. Reasonable and stable, but they're my interpretation of what the model found — the algorithm doesn't name anything.
- **Tests cover the pure logic, not the full pipeline.** 31 tests on the risk metrics, the normalization layer, and the forecast uncertainty property — the places where a regression would fail silently rather than crash. Ingestion and the API are still verified by hand. `python -m pytest`
- **SQLite.** Fine for a single batch writer. Would need Postgres for concurrent access; the ORM is there specifically so that's a connection-string change.

---

## Stack

Python 3.13 · yfinance · pandas · SQLAlchemy + SQLite · scikit-learn · statsmodels · FastAPI · React (Vite) · plain CSS

No chart library — the price charts and the small volatility "pulse" lines under each carousel title are hand-written SVG, which meant I could make the forecast band and the hover readout behave exactly how I wanted.

---

## What I'd do next

Tests first. Then Postgres and a scheduler, so ingestion actually runs nightly instead of when I remember. After that, the one place NLP genuinely belongs: summarising each company's business description into a sentence a beginner can use, which is a real text task, unlike the metric explainers.
