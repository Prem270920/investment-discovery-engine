/**
 * Pure helpers for the benchmark hero: scaling closes into chart space,
 * building the SVG paths, picking the point under the pointer, and the text
 * formats for levels, dates and change.
 */

/**
 * Closes mapped into a width x height box, oldest on the left. The vertical
 * range gets a little headroom so the line never touches the edges.
 * Returns { coords: [{x, y}], low, high }.
 */
export function scalePoints(closes, width, height, headroom = 0.08) {
  const low = Math.min(...closes);
  const high = Math.max(...closes);
  const span = high - low || 1;
  const bottom = low - span * headroom;
  const top = high + span * headroom;
  const lastIndex = Math.max(closes.length - 1, 1);
  const coords = closes.map((close, index) => ({
    x: (index / lastIndex) * width,
    y: height - ((close - bottom) / (top - bottom)) * height,
  }));
  return { coords, low, high };
}

export function linePath(coords) {
  return coords.map(({ x, y }, index) => `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
}

/** The line closed down to the baseline, for the soft fill beneath it. */
export function areaPath(coords, height) {
  if (coords.length === 0) return "";
  const first = coords[0];
  const last = coords[coords.length - 1];
  return `${linePath(coords)} L${last.x.toFixed(2)} ${height} L${first.x.toFixed(2)} ${height} Z`;
}

/** Index of the point nearest a horizontal position given as 0..1 across the chart. */
export function nearestIndex(fraction, count) {
  if (count <= 0) return -1;
  const clamped = Math.min(Math.max(fraction, 0), 1);
  return Math.round(clamped * (count - 1));
}

/** Percent change from the first close to the given one. */
export function percentChange(firstClose, close) {
  return ((close - firstClose) / firstClose) * 100;
}

const levelFormat = new Intl.NumberFormat("en-AU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
// Stored dates are plain calendar days, so format them in UTC to stop the
// viewer's time zone shifting them by a day.
const dateFormat = new Intl.DateTimeFormat("en-AU", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export const formatLevel = (close) => levelFormat.format(close);
export const formatDate = (isoDate) => dateFormat.format(new Date(`${isoDate}T00:00:00Z`));
export function formatChange(percent) {
  const sign = percent > 0 ? "+" : percent < 0 ? "−" : "";
  return `${sign}${Math.abs(percent).toFixed(1)}%`;
}
