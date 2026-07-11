# Investment Discovery Engine

A beginner-friendly, "Netflix-style" discovery tool for stable, long-term
investments across the ASX (Australia), US markets, and global ETFs.

## The Problem

Beginners who want to invest in stable long-term assets face a wall of jargon,
scattered data sources, and no personalized starting point. The research-and-triage
work — pulling asset data, computing risk metrics, filtering by locality, and
explaining each option in plain language — is manual and intimidating.

This project automates that triage and presents the results as browsable,
themed carousels (e.g. "Top Safe-Haven ETFs", "Stable Dividends in Australia"),
with plain-language explainers and educational forecasts.

> **Not financial advice.** This is an educational discovery and literacy tool.
> All projections are clearly labeled as educational, not personalized advice.

## Architecture (Full Flow)

Ingestion → Processing → Storage → Serving (API) → Frontend

- **Ingestion:** scheduled end-of-day batch pull via `yfinance` (ASX + US + global)
- **Processing:** validation, normalization, feature engineering (Beta, Sharpe,
  volatility), ML (clustering, ranking, forecasting), NLP explainers
- **Storage:** SQLite (dev) via SQLAlchemy, structured for a Postgres migration
- **Serving:** FastAPI REST API with auto-generated docs
- **Frontend:** React (Vite) — Netflix-style carousels and knowledge cards

## Key Design Decisions

### Data source: yfinance
The only free option covering ASX + US + global in one interface. Trade-off: it's
an unofficial feed with known data-quality quirks, which we handle explicitly with
a validation/normalization layer during ingestion rather than trusting it blindly.

### Serve from our own storage, never live-call the source
Ingestion is a scheduled batch job that accumulates data; the app always reads from
our database. This gives caching, resilience against feed outages, and a clean
ingestion/serving separation. Delayed EOD data is appropriate for a long-term
investment tool.

### Listing exchange ≠ underlying market
yfinance tells us where an asset is *listed*, but not what it actually *holds*.
IVV.AX is ASX-listed and AUD-priced, yet holds 100% US companies (it tracks the
S&P 500). A naive "tag .AX as Australian" rule would mislabel it as a local pick.

We maintain a small curated `underlying_market` override map. Because the asset
universe is a curated beginner shortlist (dozens, not thousands), this is tractable
— and it drives both the display tags *and* benchmark selection for beta.

### Compute risk metrics ourselves, don't trust vendor fields
yfinance returns `beta = None` for **every ETF** (confirmed across our sample).
Since ETFs are central to a beginner-focused tool, we compute volatility, Sharpe,
and beta ourselves from accumulated price history. This works uniformly for stocks
and funds, and is transparent rather than a black-box vendor number.

### Storage: SQLite + SQLAlchemy, accumulating not overwriting
Prices are treated as immutable historical facts: each run inserts only dates we
don't already have, enforced by a `UNIQUE(symbol, date)` constraint so duplicates
are structurally impossible, not merely avoided by careful code. Assets are
upserted by symbol. The database *accumulates* history over time rather than
resetting to whatever the feed offers today.

## Case Study: Debugging Cross-Market Beta

The most instructive problem in this project. Worth reading if you want to see how
decisions were made.

**The symptom.** IVV.AX (ASX-listed, tracks S&P 500) returned a beta of **0.03**
against ^GSPC. Its US-listed twin IVV returned **1.02**. Same fund, same benchmark
— so 0.03 was impossible, not merely surprising. Cross-checking against the twin is
what surfaced the bug; in isolation, 0.03 might have passed as "interesting."

**Hypothesis 1 — timezone misalignment.** ASX and US markets trade on offset
calendars, so daily returns joined by date compare different days' information.
Fix: resample both series to weekly (W-FRI). Result: beta 0.03 → **0.34**. Big
improvement, still wrong.

**Hypothesis 2 — currency dilution.** IVV.AX is AUD-priced while ^GSPC is USD, so
AUD/USD movements partially offset the underlying's moves. Fix: convert IVV.AX's
closes to USD via AUDUSD=X before computing returns. Result: 0.34 → **0.67**.
Better, still not ~1.0.

**Hypothesis 3 — inverted FX conversion.** Tested by computing both `price × rate`
and `price ÷ rate`. Divide produced correlation **−0.007** — catastrophically
worse. Hypothesis rejected; multiply was correct.

**Diagnosis.** A lag test (correlation at shifts −2…+2) showed lag 0 was already
optimal, ruling out any residual timing offset. But the decisive test was comparing
IVV.AX(USD) against IVV directly — *the same fund in the same currency* — which
correlated only **0.67**, when it should be ~0.99. Since the control (IVV vs ^GSPC
= **0.996**) proved the method itself was sound, the fault had to be in the
conversion. Root cause: yfinance's daily FX bar and the ASX equity close are
snapped at **different times of day**, so multiplying them strips some currency
effect while injecting fresh timing noise. The free data cannot support a clean
currency strip.

**The decision.** Rather than keep tuning toward a number we had pre-decided was
"right" — which for a financial figure is how you end up fooling yourself — we
**dropped the conversion and report the FX-inclusive beta**, clearly documented.

This is defensible because **0.33 is a real number**: an Australian holding an
unhedged AUD-priced S&P 500 fund genuinely does *not* get 1:1 S&P exposure.
Currency movements dilute it. That dilution is the investor's lived experience, not
an artifact. The gap between IVV.AX (0.33) and IVV (1.02) becomes a *teaching
moment* for the Knowledge Cards rather than a bug swept under the rug.

## What I'd Improve Next

- **Cross-currency beta:** with a paid feed providing FX rates snapped at market
  close, a clean currency-stripped beta becomes possible. Storing both (lived vs
  underlying exposure) would make the FX effect explicit and educational.
- **Risk-free rate:** currently fixed per-market constants. Fetching live short-term
  government bond yields would be more precise (though the effect on *relative*
  rankings is marginal).
- **Postgres migration:** SQLAlchemy ORM was chosen specifically so this is a
  connection-string change, not a rewrite. Triggered when the asset universe or
  concurrency grows.
- **Monitoring:** ingestion currently logs failures and summarizes each run.
  Production would alert on repeated failures or stale data.