/**
 * How each line on the projection and replay charts is drawn.
 *
 * Colour only ever means risk, so the real price and the two models are told
 * apart by line style and by name: solid for what really happened, dashed for
 * ARIMA, dotted for the GRU. All three stay in neutral greys.
 */
export const FORECAST_LINES = {
  actual: {
    label: "Real price",
    stroke: "var(--data-line)",
    width: 2,
    dash: undefined,
  },
  arima: {
    label: "ARIMA",
    stroke: "var(--ink-muted)",
    width: 1.8,
    dash: "6 4",
  },
  gru: {
    label: "GRU",
    // A lighter grey than ARIMA's, so the two still read apart where their
    // dashes overlap. Mixed from existing greys rather than adding a colour.
    stroke: "color-mix(in srgb, var(--data-line) 72%, var(--bg-panel))",
    width: 2.2,
    // A near zero dash with round caps draws a row of dots.
    dash: "0.1 4.5",
  },
};

/** The forward projection for one lens as chart points with their band. */
export function lensPoints(lens) {
  if (!lens) return [];
  return lens.path.map((day, position) => ({
    date: day.date,
    predicted: day.predicted,
    lower: lens.band[position].lower,
    upper: lens.band[position].upper,
  }));
}
