# Investment Discovery Engine

A browsing tool for people who want to start investing and don't know where to look. Instead of a spreadsheet with 40 columns, it groups assets into themed rows ("Safe & Steady", "Income Generators", "Higher-Risk Growth") and explains each one in plain English.

The categories aren't hand-written. They come out of a clustering model trained on risk behaviour, so an energy ETF can end up sitting next to Coca-Cola if that's how they actually move.

> **This is an educational tool, not financial advice.** Nothing here is a recommendation to buy anything. The price projections in particular are illustrations of a statistical trend, not predictions. More on that below.

---

## The problem I was actually solving

If you've never invested before, the hard part isn't the buying. It's that there are thousands of options, the data is scattered, and every source assumes you already know what beta means.

The manual version of this is what a curious beginner does over a weekend: look up some ETFs, try to figure out which ones are "safe", squint at a chart, give up. This automates that triage: it pulls the data, computes the risk metrics, groups similar assets together, and writes the explanation.

Australia + US + global, because I'm in Melbourne and most tools are US-only.

---

## What's in the app

The interface is built as an interactive data story: the page explains, and you steer by scrolling, hovering and tapping.

- **Themed rows from a clustering model**, each with a **risk spread strip**: one dot per asset on a calm to volatile track, so a row's risk mix shows at a glance. Point at a dot and its card lights up.
- **The market backdrop**: the S&P 500's year at the top, for context.
- **Asset cards** with a risk chip, a three month sparkline and its change, and a plain explanation of the Sharpe ratio.
- **A four part story for each asset**: what it is, how it moves, what might happen, and similar assets, with a sticky index to jump between them. Summaries are in plain English, with a glossary for the jargon.
- **Two forecasts and a backtest race**: ARIMA and a GRU neural network each project 30 days ahead. Replay the test both sat and watch their predictions draw beside the real price, then see who won, or whether it was too close to call.
- **Colour only ever means risk.** Price lines are one neutral colour and direction is shown by the + or minus sign. Motion is extra, never required: with reduced motion on, everything shows its final state, and every control is keyboard reachable.

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

Add `--skip-forecasts` to the pipeline command for a faster run. The ARIMA stage is the slow part. Skipped stages keep whatever forecasts are already stored.

The GRU lens (more on it below) needs PyTorch, which lives in a separate requirements file so the app still runs without it:

```bash
pip install -r requirements-ml.txt
```

Without torch, or with `DISCOVERY_DISABLE_TORCH=1` set, the pipeline marks every asset's GRU as skipped and the app shows ARIMA alone. `--skip-neural` skips the GRU stage on purpose. To print the head to head comparison after a run:

```bash
python -m src.ml.lens_report
```

### In production

In production there's one server. Build the frontend once, then FastAPI serves the app at `/` and the API under `/api` from the same address, so there's no Vite and no CORS to configure:

```bash
cd frontend && npm ci && npm run build && cd ..
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

No `--reload` here: that's a development convenience that watches files and restarts. Use whatever port your host gives you. If `frontend/dist` is missing, the API still starts, logs one warning, and serves only `/api`.

Settings come from environment variables, and none are needed to run locally:

| Variable | Default | What it sets |
|---|---|---|
| `DISCOVERY_DATABASE_PATH` | `data/investments.db` | The SQLite file. Relative paths start from the repo root. |
| `DISCOVERY_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma separated origins allowed to call the API from another address. Set it empty when the API serves the frontend itself. |
| `DISCOVERY_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. An unknown value stops startup with a message. |
| `DISCOVERY_DISABLE_TORCH` | unset | Set to `1` to run the pipeline without the GRU lens. |

---

## How it fits together

```
yfinance  →  validate  →  SQLite  →  metrics  →  cluster  →  forecasts  →  FastAPI  →  React
                ↓                       ↓           ↓            ↓
          override map            vol/Sharpe/beta  frozen     ARIMA, then a
          for bad vendor data                      model      GRU scored on the
                                                              same held out days
```

Everything is a batch job. The app never calls yfinance at request time; it reads from its own database. That means it stays up when Yahoo doesn't, and it isn't hostage to rate limits.

The pipeline runs its stages inside a single transaction: ingest assets, ingest benchmarks, compute metrics, assign clusters, ARIMA forecasts, GRU forecasts (stage 5b), plain English descriptions. If any stage fails the whole thing rolls back, so you never end up with assets but no metrics. The GRU stage is the exception that proves the rule: a missing torch or one asset's failed training is recorded per asset and the run carries on, because an optional model shouldn't be able to sink the data everything else depends on.

**56 assets, ~14,000 price bars, six clusters.**

---

## Three things that went wrong

This is the part I'd actually want to talk about in an interview.

### The beta that was impossible

IVV.AX is an ASX-listed ETF that holds the S&P 500. Its US-listed twin, IVV, is literally the same fund. Measured against the S&P 500, IVV came out at beta 1.02, which is correct. IVV.AX came out at **0.03**.

Not surprising. Impossible. A fund that holds the S&P 500 cannot be uncorrelated with the S&P 500. I only caught it because I had the twin sitting right there to compare against.

What followed was three hypotheses, each tested rather than assumed:

1. **Timezone misalignment.** The ASX closes before New York opens, so joining daily returns by calendar date compares different days' information. Resampling both to weekly moved beta from 0.03 → 0.34. Better, still wrong.
2. **Currency dilution.** IVV.AX is priced in AUD; the S&P 500 is in USD. Converting the prices to USD first moved it to 0.67. Better, still wrong.
3. **Inverted conversion.** Maybe I was multiplying where I should have divided? Tested both. Dividing gave a correlation of −0.007, which was catastrophically worse. Hypothesis dead.

The test that settled it: comparing IVV.AX (converted to USD) against IVV directly. Same fund, same currency, so they should correlate ~0.99. They correlated **0.67**. Since the control (IVV against the index) came out at 0.996, the method was fine. The conversion was the broken link.

Root cause: yfinance's daily FX bar and the ASX equity close are snapped at different times of day. Multiplying them strips some of the currency effect while injecting fresh timing noise. **The free data can't support a clean currency conversion.**

So I stopped, and reported the FX-inclusive number instead. That's defensible because **0.33 is a real number**: an Australian holding an unhedged AUD-priced S&P 500 fund genuinely does not get 1:1 exposure to the S&P 500. Currency movements dilute it. That dilution is the investor's actual experience, not an artifact.

The app now explains this gap to the user on the asset page. What started as a bug became the best teaching moment in the product.

I later added IHVV.AX, the currency-*hedged* version of the same fund, as a natural experiment. Its beta came out roughly double the unhedged one, which supports the currency explanation without fully closing the gap. The rest is the timing effect I couldn't fix.

### Carousels that reshuffled every run

The first version refit KMeans on every pipeline run. Since it trains on live market data, and market data moves, the clusters redrew themselves each time. One run labelled the entire bond cluster "Recent Underperformers". That was technically true (bonds had the worst Sharpe in a rising market) and completely useless as a category.

The fix was to separate training from inference, which is how this is supposed to work anyway. `train_clusters.py` fits the scaler and the model, derives the labels from the centroids, and saves all three as a versioned artifact. The pipeline loads that artifact and calls `.predict()`, never `.fit()`. Same model in, same categories out.

The labels are frozen inside the artifact too, which killed a second bug: the rules that assign human names to clusters were being re-evaluated each run against shifting centroids, so a category could silently change meaning between runs.

Rule ordering turned out to matter more than I expected. An early version claimed "Higher-Risk Growth" by highest volatility, which grabbed a two-asset cluster that was volatile because it had *crashed* (Sharpe −1.28). Growth now keys on beta, and "Safe & Steady" gets claimed before "Underperformers" so bonds don't get mislabelled in a bull market.

### A pipeline that lied about succeeding

The run summary printed `metrics computed: 56`. The database had zero rows.

During a refactor I'd lost the `session.commit()`. Every run staged its work, logged success, then closed the session and threw it all away. The logs cheerfully reported a completed run the entire time.

I found it by checking `SELECT COUNT(*)` instead of trusting the summary. That habit (verify the outcome, not the log) has caught more in this project than anything else.

---

## The forecasts, and why they're honest

Every asset page shows a 30-day price projection. I want to be direct about what that is.

Forecasting asset prices is not reliably possible. If it were, none of us would need jobs. So the goal was never accuracy. It was building something that shows its own uncertainty rather than hiding it.

Two things make it honest.

**The confidence band widens.** Uncertainty compounds: being unsure about tomorrow is very different from being unsure about six weeks out. Variance grows with the number of steps, so the band grows with √n. For VAS.AX it goes from 3.38 wide on day one to 18.64 by day thirty. You can watch it fan out. That's the lesson, delivered visually.

**Each forecast reports its own measured error.** I hold out the last 30 days, train on everything before that, and check how far off the projection was on data the model never saw. That number goes on the page. For VAS.AX it reads: *"Tested on the most recent 30 days it had never seen, this model's projections were off by about 2.24% on average."*

The error broadly tracks risk, which is the nicest validation of the whole thing. Across all 56 assets the rank correlation between backtest error and volatility is 0.69, and the median error climbs from 1.54% for the "Very low risk" assets to 6.63% for the "Very high risk" ones. Single assets don't always follow it, though: in this run AAPL's error came in just below BND's. Prices run through 25 November 2026:

| Asset | Risk tier | Backtest error |
|---|---|---|
| SHY (short treasuries) | Very low | 0.44% |
| BND (total bond market) | Very low | 1.41% |
| VOO (S&P 500) | Low | 4.46% |
| AAPL | Very high | 1.38% |
| CSL.AX | Very high | 6.63% |

The model is measurably better at boring assets and worse at exciting ones. That isn't a disclaimer, it's evidence: "trust this less for TSLA" becomes something the app can *demonstrate* rather than assert.

Under the hood it fits two competing models per asset (ARIMA on prices and ARIMA on returns), with the order auto-selected by AIC, backtests both, and keeps whichever won. Across 56 assets, 36 went with the price model and 20 with the returns model, so both approaches are earning their place rather than one always winning.

---

## Second forecasting lens

ARIMA is a classic statistical model. I wanted to know whether a neural network does any better on the same job, so every asset now also gets a GRU forecast, and the two are judged head to head on the same 30 days neither model saw in training. The asset page shows both projections, replays the test day by day, and says who won.

### Why a GRU, and why such a small one

The data is the constraint. Each asset has about a year of daily prices: 254 to 258 bars. Hold out 30 days for the test, turn the rest into daily returns and cut those into 30 day windows, and the GRU gets about 156 training windows per asset. That is tiny for a neural network.

So the model is deliberately small: 32 hidden units and 3,393 trainable weights in total, trained with early stopping on a validation slice and a fixed seed so reruns give the same answer. A GRU rather than an LSTM because it has fewer moving parts for the same idea, which matters when there's this little to learn from. Anything bigger would memorise the year rather than learn from it.

### Per asset now, global later

Each asset's GRU trains on that asset's history alone. One model trained across all 56 assets would see about 8,700 windows instead of about 156, which is the obvious answer to the data problem. It also raises questions the per asset version doesn't: does a bond fund's history help forecast NVIDIA? Starting per asset keeps each result readable. The windowing code already takes a list of price series rather than one, so pooling them into a global model is a small change when I want to test it.

### Same test, same rules

The comparison is only fair if both models sit the same exam. They're scored on the same 30 held out days with the same error measure (RMSE as a percent of price). The GRU predicts daily returns and turns them back into prices exactly the way ARIMA's returns model does, and its band is set to the same 95% confidence level and widens the same way. The pipeline records the verdict once, and the API and the app read it from there.

A gap under 0.05 percentage points is recorded as **too close to call** rather than a win. The errors are stored to two decimals and come from a single 30 day test, which can't separate two models that close.

### The result

From `python -m src.ml.lens_report`, run on 25 November 2026 with prices through that day. Every data refresh moves these numbers, so once the data updates nightly, rerun the report for current ones:

```
Second forecasting lens: GRU against ARIMA on the same 30 held out days
Prices through 2026-11-25
Assets compared: 56 (not compared: 0)

Outcomes
  ARIMA wins          35
  GRU wins            15
  Too close to call    6

Median backtest error (RMSE, percent of price)
  ARIMA   4.01%
  GRU     4.71%

Median backtest error by cluster
  Cluster                     Assets    ARIMA      GRU
  Broad Market Core               14    2.69%    3.72%
  Higher-Risk Growth               7    4.27%    6.31%
  Income Generators               15    4.33%    4.32%
  Market-Neutral Defensives        8    5.94%    5.44%
  Recent Underperformers           5    6.63%    7.54%
  Safe & Steady                    7    1.41%    1.27%

Biggest GRU wins (margin in percentage points)
  PG       ARIMA   7.62%  GRU   5.84%  margin  1.78
  JNJ      ARIMA   7.31%  GRU   5.91%  margin  1.40
  KO       ARIMA   3.90%  GRU   2.89%  margin  1.01
  XLU      ARIMA   3.19%  GRU   2.68%  margin  0.51
  XLP      ARIMA   5.51%  GRU   5.03%  margin  0.48

Biggest ARIMA wins (margin in percentage points)
  NVDA     ARIMA  24.91%  GRU  32.65%  margin  7.74
  BHP.AX   ARIMA   8.92%  GRU  12.99%  margin  4.07
  XLE      ARIMA   6.36%  GRU   9.67%  margin  3.31
  RIO.AX   ARIMA  10.20%  GRU  12.50%  margin  2.30
  MQG.AX   ARIMA   4.27%  GRU   6.31%  margin  2.04
```

### An honest reading

**The neural network is not the better forecaster here.** ARIMA won 35 assets, the GRU 15, and 6 were too close to call. The median error is 4.01% for ARIMA against 4.71% for the GRU. With about 156 training windows per asset, that's roughly what I'd expect: the simpler model has fewer ways to go wrong on so little data.

**But where it loses isn't random.** All five of the GRU's biggest wins (PG, JNJ, KO, XLU, XLP) sit in the Market-Neutral Defensives cluster: household goods, healthcare, drinks, utilities and staples. It also has the lower median error in Safe & Steady (1.27% against 1.41%) and Market-Neutral Defensives (5.44% against 5.94%), and is level in Income Generators (4.32% against 4.33%). ARIMA's biggest wins are the big movers: NVDA, the miners BHP.AX and RIO.AX, MQG.AX and the energy ETF XLE, and it leads clearly in Higher-Risk Growth (4.27% against 6.31%). The same defensive cluster holds XLE, though, so cluster membership alone isn't the story. My guess is that on so little data the GRU learns something close to "daily returns are small and drift back", which suits calm assets and fails on ones making large sustained moves. That's a hypothesis I haven't tested.

**It's one 30 day test, and it moves.** These numbers come from a single window of held out days, so read them as this month's exam rather than a law. Between two runs one trading day apart, AAPL went from too close to call (ARIMA 1.63%, GRU 1.62%) to a clear ARIMA win (1.38% against 1.48%), simply because the held out window moved forward by a day.

**Even the inputs move.** While building this I ran the pipeline twice a few minutes apart, with both markets closed, expecting identical results. yfinance returned different adjusted closes for 1,891 of the 14,938 stored price rows across 46 symbols, almost all by less than one part in two million. Noise that small was enough to change ARIMA's chosen order for VAP.AX from (1,1,1) to (2,1,2), and to move backtest errors by up to 0.09 percentage points (IVV.AX from 2.23% to 2.31%; KO from 5.91% to 5.82%, with only two of its prices revised). That is bigger than the 0.05 point too close threshold, so a revision alone can flip a close head to head result. It's another reason not to crown a winner on a tiny gap. It's also why, when I check that a code change didn't alter ARIMA's results, I compare runs on a copy of the database with prices held fixed, never two fresh fetches.

---

## Decisions worth explaining

**Where an asset is listed isn't what it holds.** yfinance tells you IVV.AX trades on the ASX in AUD. It doesn't tell you it holds 500 American companies. A naive "`.AX` means Australian" rule mislabels it, and then the Australia filter shows you a US fund.

So there's a curated override map, but only for the exceptions. Eleven entries covering 56 assets. Individual stocks don't need one (an ASX-listed company *is* Australian); ETFs are the problem, because an ETF is a wrapper that can hold anything. The map is short enough to read in a glance, and every line documents a case where the obvious rule breaks.

**The universe is curated on purpose.** I could auto-fetch the ASX 200 and S&P 500 and have 700 assets. I deliberately didn't. The app exists because beginners can't navigate hundreds of options, and dumping 700 on them recreates the exact problem it's meant to solve. Curation *is* the product. It's also the only way to keep the exposure labels correct, since nothing in the free data tells you what an unfamiliar ETF actually holds.

The list lives in `config/universe.yaml`, so scaling up is a config change rather than a code change.

**Risk metrics are computed, not fetched.** yfinance returns `beta = None` for every single ETF I tested. Since ETFs are most of what a beginner should be looking at, that field is useless. Volatility, Sharpe and beta are all computed from stored price history instead. That works identically for funds and stocks, and I can explain exactly how each number was derived.

**Clustering doesn't see the labels.** The model gets volatility, Sharpe, beta and dividend yield. It does *not* get asset type, sector, or country, because then it would mostly rediscover the categories I already had. Leaving them out is why the "Market-Neutral Defensives" row contains a utilities ETF, an energy ETF, Johnson & Johnson and Coca-Cola, grouped only by the fact that they all move independently of the market. No conventional taxonomy puts those four together.

**The explainers are templated, not generated.** They read like prose but they're rule-based, assembled from the computed metrics. I considered an LLM and decided against it: in a finance tool aimed at beginners, a model that occasionally invents a fact is worse than one that's slightly stiff. Everything on the page traces back to a number in the database.

---

## Known limitations

- **Cross-currency beta is FX-inclusive.** Documented above. Fixing it properly needs FX rates snapped at market close, which the free feed doesn't provide.
- **Risk tiers are relative to this universe.** They're quintiles, so "Very low risk" means "among the calmest fifth of the 56 assets here", not an absolute claim about the market.
- **Cluster labels are heuristics.** Rules applied to centroids, ranked against each other. Reasonable and stable, but they're my interpretation of what the model found. The algorithm doesn't name anything.
- **Tests cover the logic, the API and the interface, not live ingestion.** 153 backend tests with pytest (144 in the fast suite, plus 9 slow ones that fit real ARIMA models or train the GRU) and 153 frontend tests with Vitest and Testing Library. They cover the risk metrics, normalisation, both forecasting lenses, storage, the pipeline's skip flags, the carousel, benchmark, forecast and health endpoints, and the interface components. Fetching from yfinance is still checked by hand, by running the pipeline and counting rows. `python -m pytest -m "not slow"` and `cd frontend && npm test`
- **SQLite.** Fine for a single batch writer. Would need Postgres for concurrent access; the ORM is there specifically so that's a connection-string change.

---

## Stack

Python 3.13 · yfinance · pandas · SQLAlchemy + SQLite · scikit-learn · statsmodels · PyTorch (optional, for the GRU) · FastAPI · React (Vite) · CSS Modules · pytest · Vitest + Testing Library

No chart library and no animation library: the price charts, the risk spread strips and the backtest race are hand-written SVG, and the motion is CSS transitions plus `requestAnimationFrame`. That meant I could make the forecast bands, the hover readouts and the replay behave exactly how I wanted.

---

## What I'd do next

Deployment first: the API and the frontend hosted, with Postgres and a scheduler so ingestion actually runs nightly instead of when I remember.

Then a Q&A layer: ask a question in plain English ("which bond funds held up best this year?") and get an answer built from the stored data, where every number is checked against the database before it's shown. It will be the one part of the app allowed to call out to the network at request time.
