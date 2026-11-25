import { useState } from "react";
import { lensPoints } from "../forecastLines";
import { formatErrorPct, headToHeadSentence, verdictBadge } from "../headToHead";
import BacktestRace from "./BacktestRace";
import LineKey from "./LineKey";
import PriceChart from "./PriceChart";
import cardStyles from "./KnowledgeCard.module.css";
import styles from "./OutlookSection.module.css";

const LENS_CHOICES = [
  { id: "arima", label: "ARIMA" },
  { id: "gru", label: "GRU" },
  { id: "both", label: "Both" },
];

const PROJECTION_LABELS = { arima: "ARIMA projection", gru: "GRU projection" };

/**
 * The "What might happen" part of the Knowledge Card: the forward projection
 * for the chosen model, then a replay of the 30 day test both models sat,
 * then who did better.
 *
 * Without a GRU result there is nothing to choose between, so the toggle and
 * the head to head line are left out and the replay shows ARIMA alone.
 */
export default function OutlookSection({ forecast, history, currency }) {
  const [lensChoice, setLensChoice] = useState("arima");

  const lenses = forecast.lenses;
  const gruLens = lenses?.gru ?? null;
  const shownLens = gruLens ? lensChoice : "arima";

  // Older responses only carry points, which are the ARIMA projection.
  const arimaProjection = { id: "arima", points: lenses ? lensPoints(lenses.arima) : forecast.points };
  const gruProjection = gruLens ? { id: "gru", points: lensPoints(gruLens) } : null;
  const projections = {
    arima: [arimaProjection],
    gru: [gruProjection],
    both: [arimaProjection, gruProjection],
  }[shownLens];
  const shownModelIds = projections.map((projection) => projection.id);

  const days = forecast.horizon_days;
  // The pipeline decides the verdict; this only shows it.
  const headToHead = gruLens ? forecast.head_to_head : null;
  const badge = verdictBadge(headToHead?.winner);
  const sentence = headToHeadSentence(headToHead);

  const headToHeadLine = badge && sentence && (
    <p className={styles.headToHead} data-testid="head-to-head">
      <span className={styles.badge} data-verdict={headToHead.winner}>{badge}</span>{" "}
      {sentence}
    </p>
  );

  const backtest = forecast.backtest;
  const testDays = backtest?.actual.length ?? 30;

  return (
    <>
      {gruLens && (
        <div className={styles.toggle} role="group" aria-label="Projection model">
          {LENS_CHOICES.map((choice) => (
            <button
              key={choice.id}
              type="button"
              className={`${styles.toggleButton} ${shownLens === choice.id ? styles.toggleOn : ""}`}
              aria-pressed={shownLens === choice.id}
              onClick={() => setLensChoice(choice.id)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}

      <LineKey lineIds={["actual", ...shownModelIds]} labels={PROJECTION_LABELS} />
      <PriceChart
        points={history}
        projections={projections}
        currency={currency}
        changeLabel={null}
        description={`Projection chart: the last three months of prices and the next ${days} trading days from ${
          shownModelIds.map((modelId) => (modelId === "gru" ? "the GRU" : "ARIMA")).join(" and ")
        }, with a shaded range of plausible outcomes`}
      />

      <div className={cardStyles.forecastNote}>
        <ProjectionExplainer shownLens={shownLens} forecast={forecast} days={days} gruLens={gruLens} />
      </div>

      <div className={styles.test}>
        <h3 className={cardStyles.explainerTitle}>The {testDays} day test</h3>
        <p className={cardStyles.para}>
          Before projecting forward, {gruLens ? "each model was" : "the model was"} trained without
          the last {testDays} trading days and asked to predict them. The solid line is what
          really happened.
        </p>
        {backtest ? (
          <BacktestRace backtest={gruLens ? backtest : { ...backtest, gru: null }}>
            {headToHeadLine}
          </BacktestRace>
        ) : (
          headToHeadLine
        )}
      </div>
    </>
  );
}

function ProjectionExplainer({ shownLens, forecast, days, gruLens }) {
  const arimaFit = forecast.method === "returns" ? "fitted to daily returns" : "fitted to prices directly";

  if (shownLens === "both") {
    return (
      <>
        <h3 className={cardStyles.explainerTitle}>Two projections</h3>
        <p className={cardStyles.para}>
          The dashed line is ARIMA, a classic statistical model {arimaFit}. The dotted line is a
          GRU, a small neural network trained on this asset's daily returns. Each carries its own
          shaded range, and both widen the further out they go, because uncertainty compounds.
        </p>
      </>
    );
  }

  const isGru = shownLens === "gru";
  const errorPct = isGru ? gruLens.rmse_pct : forecast.backtest_error_pct;
  return (
    <>
      <h3 className={cardStyles.explainerTitle}>{isGru ? "The dotted projection" : "The dashed projection"}</h3>
      {isGru ? (
        <p className={cardStyles.para}>
          The dotted line projects {days} trading days ahead using a GRU, a small neural network
          trained on this asset's daily returns. The shaded band with a dotted edge shows the range
          of plausible outcomes. It gets wider the further out it goes, because uncertainty compounds.
        </p>
      ) : (
        <p className={cardStyles.para}>
          The dashed line projects {days} trading days ahead
          using an ARIMA model {arimaFit}. The shaded band shows the range of plausible outcomes. Notice it
          gets wider the further out it goes, because uncertainty compounds.
        </p>
      )}
      {errorPct != null && (
        <p className={cardStyles.para}>
          <strong>How much should you trust it?</strong> Tested on the most
          recent 30 days it had never seen, this model's projections were off
          by about{" "}
          <span className={`tnum ${cardStyles.figure}`}>{formatErrorPct(errorPct)}</span>
          {" "}on average. Treat it as an illustration of a statistical trend,
          not a prediction of what will happen.
        </p>
      )}
    </>
  );
}
