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

- **yfinance** as the data source: the only free option covering ASX + US + global
  in one interface. Trade-off: it's an unofficial feed with known data-quality
  quirks (dividend-yield unit inconsistency, occasional stale fundamentals), which
  we handle explicitly with a validation/normalization layer during ingestion.
- **Serve from our own storage, never live-call the source:** gives caching,
  resilience, and a clean ingestion/serving separation. Delayed EOD data is fine
  for a long-term investment tool.
- **SQLite + SQLAlchemy:** zero-setup for anyone cloning the repo; ORM keeps the
  Postgres migration a config change, not a rewrite.

## Status

🚧 In active development. See commit history for the step-by-step build.

## What I'd Improve Next

- Migrate SQLite → Postgres for concurrent access
- Add monitoring/alerting on ingestion failures
- Expand ML forecasting beyond baseline models